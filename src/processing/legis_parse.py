import re
from typing import List, Literal, Optional, TypedDict, Union


# TODO: Why is pylint erroring on this import?
from lxml.etree import _Element as LXMLElement  # pylint: disable=no-name-in-module


class ParsingState(TypedDict):
    first_enum_found: bool
    first_header_found: bool
    section_number: Optional[int]
    header: str


class EnumMask(TypedDict):
    type: Literal["ENUM"]
    original_text: str


MaskEntry = EnumMask


class ExternalXrefTag(TypedDict):
    type: Literal["EXTERNAL_XREF"]
    enclosed_text: str
    legal_doc: str
    parsable_cite: str


class QuoteTag(TypedDict):
    type: Literal["QUOTE"]
    enclosed_text: str


class QuotedBlockTag(TypedDict):
    type: Literal["QUOTED_BLOCK"]
    enclosed_text: str


TagEntry = Union[ExternalXrefTag, QuoteTag, QuotedBlockTag]


def preprocess(normalized_output):
    # Apply basic normalization without masking important elements
    normalized = normalize_punctuation(normalized_output)

    # Tokenize
    tokens = tokenize_normalized_output(normalized)

    return tokens


def tokenize_normalized_output(normalized_output):
    # Preserve special tags as single tokens
    # Replace tag spaces temporarily
    temp = normalized_output
    for tag_type in ["QUOTE", "QUOTED_BLOCK", "EXTERNAL_XREF"]:
        temp = temp.replace(f"<{tag_type}>", f" <{tag_type}> ")
        temp = temp.replace(f"</{tag_type}>", f" </{tag_type}> ")

    # Split by whitespace and filter empty strings
    tokens = [t for t in temp.split() if t]

    return tokens


def normalize_punctuation(text):
    # Standardize dashes
    text = text.replace('—', '-').replace('–', '-')

    # Remove trailing punctuation from words except when it matters
    # (keep period in "U.S." but remove trailing commas/semicolons)
    words = []
    for word in text.split():
        if word[-1] in [',', ';'] and len(word) > 1:
            words.append(word[:-1])
        else:
            words.append(word)

    return ' '.join(words)


def is_descendant(node: LXMLElement, tag: str) -> bool:
    """
    Determines whether the specified XML node is a descendant of a node of the specified tag.
    Args:
        node (Element): The XML node to check.
        tag (str): The tag to check if the node is a descendant of.

    Returns:
        bool: True if the node is a descendant of the tag, False otherwise.
    """
    if node.tag == tag:
        return True
    if node.getparent() is not None:
        return is_descendant(node.getparent(), tag)
    return False


def clean_section_number(section_number: str) -> Optional[int]:
    """
    Cleans and converts the section number into an integer.

    "1." -> 1

    Args:
        section_number (str): Raw section number from the XML.

    Returns:
        int: Cleaned section number, or None if conversion fails.
    """
    section_number = section_number.rstrip(".")  # Remove trailing periods
    try:
        return int(section_number)  # Convert to integer
    except ValueError:
        return None  # Return None if the section number isn't a valid integer


def normalize_whitespace(text: str) -> str:
    """
    Cleans the text by stripping leading/trailing whitespace and replacing
    multiple spaces/newlines with a single space.

    Args:
        text (str): The text to clean.

    Returns:
        str: Cleaned text.
    """
    return re.sub(r'\s+', ' ', text.strip())


def normalize_parentheses_spacing(text: str) -> str:
    """
    Given a string that may or may not contain opening and closing parentheses, ensure
    that each instance of an opening parentheses is not followed by a space, and each
    instance of a closing parentheses is not preceded by a space.
    """
    return re.sub(r' \)', ')', re.sub(r'\( ', '(', text))


def normalize_header(header: str) -> str:
    """
    Normalize header field of parsed section output.
    """
    # push to lowercase
    header = header.lower()

    # normalize whitespace
    header = normalize_whitespace(header)

    # remove quotes, parens, commas
    header = re.sub(r'[\"\(\),]', '', header)

    return header


def normalize_output_text(text: str) -> str:
    """
    Normalizes legislative section output text while preserving masked and tagged values,
    ensuring proper spacing and retention of parentheses where necessary.

    Args:
        text (str): The raw section text with masks and tags.

    Returns:
        str: The normalized section text.
    """

    # local normalize fn
    def normalize_text(part: str) -> str:
        # push to lower
        part = part.lower()
        # Normalize whitespace
        part = normalize_whitespace(part)
        # Strip quotes, parentheses, commas, colons, semicolons
        part = re.sub(r"[\"'(),;:]", "", part)
        return part

    # regex for tags, enclosed text inclusive (e.g., <QUOTE>...</QUOTE>)
    tag_pattern = re.compile(r"(<[^>]+>.*?</[^>]+>|<[^>]+>)")
    # regex for masks (e.g., MASK_ENUM)
    mask_pattern = re.compile(r"\bMASK_[A-Z_]+\b")

    # Split text into parts while keeping tags and masks intact
    parts = tag_pattern.split(text)

    # Normalize only the non-tag, non-mask portions
    normalized_parts = []
    for part in parts:
        if tag_pattern.match(part):
            # Ensure proper spacing around tags/masks
            if normalized_parts and not normalized_parts[-1].endswith(" "):
                normalized_parts.append(" ")  # Add leading space if necessary
            normalized_parts.append(part)
            normalized_parts.append(" ")  # Ensure trailing space
        else:
            # second split on mask pattern
            mask_parts = mask_pattern.split(part)
            for mask_part in mask_parts:
                if mask_pattern.match(mask_part):
                    normalized_parts.append(mask_part)
                else:
                    normalized_parts.append(normalize_text(mask_part))

                # ensure proper spacing
                if normalized_parts and not normalized_parts[-1].endswith(" "):
                    normalized_parts.append(" ")

    # Reconstruct the text while preserving structure
    normalized_text = "".join(normalized_parts)

    return normalized_text.strip()


def handle_enum(node: LXMLElement, state: ParsingState, masks: List[MaskEntry], output: List[str]):
    """Handles <enum> elements."""
    if not state["first_enum_found"]:  # Preserve first <enum> as section number
        raw_section_number = normalize_whitespace(
            node.text) if node.text else ""
        state["section_number"] = clean_section_number(raw_section_number)
        state["first_enum_found"] = True
    else:  # Mask all subsequent <enum> elements
        mask_enum = "MASK_ENUM"

        # Sometimes, enums will be empty nodes.
        # TODO: I'm still investigating why this happens. For an example. see 118hr2670enr Sec. 1273
        # For now, I'm going to supply a placeholder value for empty enums, such that at least something is passed along
        # to the masks array for a given section.
        if not node.text:
            placeholder = "EMPTY_ENUM_NODE"

            masks.append(
                {"type": "ENUM", "original_text": placeholder})
            output.append(mask_enum)

        else:
            masks.append(
                {"type": "ENUM", "original_text": normalize_whitespace(node.text)})
            output.append(mask_enum)


def handle_header(node: LXMLElement, state: ParsingState, output: List[str]):
    """Handles <header> elements."""
    if not state["first_header_found"]:  # Preserve first <header> separately
        state["header"] = normalize_whitespace(node.text) if node.text else ""
        state["first_header_found"] = True
    else:
        output.append(normalize_whitespace(node.text))


def handle_external_xref(node: LXMLElement, tags: List[TagEntry], output: List[str]):
    """Handles <external-xref> elements."""
    enclosed_text = normalize_whitespace(node.text) if node.text else ""
    tags.append(
        {
            "type": "EXTERNAL_XREF",
            "enclosed_text": enclosed_text,
            "legal_doc": node.attrib.get("legal-doc"),
            "parsable_cite": node.attrib.get("parsable-cite"),
        }
    )
    tagged_text = f"<EXTERNAL_XREF>{enclosed_text}</EXTERNAL_XREF>"
    output.append(tagged_text)


def handle_quote(node: LXMLElement, tags: List[TagEntry], output: List[str]):
    """Handles <quote> elements."""

    quote_text_parts = []

    def collect_text(node: LXMLElement):
        if node.text:
            quote_text_parts.append(normalize_whitespace(node.text))
        for child in node.getchildren():
            collect_text(child)
            if child.tail:
                quote_text_parts.append(normalize_whitespace(child.tail))

    collect_text(node)

    quote_text = " ".join(filter(None, quote_text_parts)).strip()
    tags.append({"type": "QUOTE", "enclosed_text": quote_text})
    tagged_text = f"<QUOTE>{quote_text}</QUOTE>"
    output.append(tagged_text)


def handle_quoted_block(node: LXMLElement, tags: List[TagEntry], output: List[str]):
    """Handles <quoted-block> elements."""
    quoted_block_text_parts = []

    def collect_text(node: LXMLElement):
        if node.text:
            quoted_block_text_parts.append(normalize_whitespace(node.text))
        for child in node.getchildren():
            collect_text(child)
            if child.tail:
                quoted_block_text_parts.append(
                    normalize_whitespace(child.tail))

    collect_text(node)

    quote_block_text = " ".join(filter(None, quoted_block_text_parts)).strip()
    tags.append({"type": "QUOTED_BLOCK", "enclosed_text": quote_block_text})
    tagged_text = f"<QUOTED_BLOCK>{quote_block_text}</QUOTED_BLOCK>"
    output.append(tagged_text)


def process_node(node: LXMLElement, state: ParsingState, masks: List[MaskEntry], tags: List[TagEntry], output: List[str]):
    """Recursively process nodes in a section."""
    if node.tag == "enum":
        handle_enum(node, state, masks, output)
    elif node.tag == "header":
        handle_header(node, state, output)
    elif node.tag == "external-xref":
        handle_external_xref(node, tags, output)
    elif node.tag == "quote":
        handle_quote(node, tags, output)
    elif node.tag == "quoted-block":
        handle_quoted_block(node, tags, output)
        return  # quoted block handler is special case that handles its own recursion, so resume process recursion on next sibling
    elif node.text:
        output.append(normalize_whitespace(node.text))

    # Process direct children, thereby depth-first recursing
    for child in node.getchildren():
        process_node(child, state, masks, tags, output)

        # Append tail text after recursing, ensuring proper text order
        # I.e., text and tails of children will be appended in order, inner to outer
        if child.tail:
            output.append(normalize_whitespace(child.tail))


def process_section(section: LXMLElement) -> dict:
    masks = []
    tags = []
    output = []

    state: ParsingState = {
        "first_enum_found": False,
        "first_header_found": False,
        "section_number": None,
        "header": "",
    }

    process_node(section, state, masks, tags, output)

    output = " ".join(filter(None, output)).strip()
    output = normalize_parentheses_spacing(output)
    section_id = section.attrib.get("id")

    normalized_header = normalize_header(state["header"])
    normalized_output = normalize_output_text(output)

    return {
        "section_id": section_id,
        "section_number": state["section_number"],
        "header": state["header"],
        "normalized_header": normalized_header,
        "masks": masks,
        "tags": tags,
        "output": output,
        "normalized_output": normalized_output,
    }
