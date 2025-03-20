"""
Bringing a punch of functions from my redlining project over to this. Generally,
the functions here are related to parsing bill XML files and extracting text.
"""

import re
import textwrap

# Strucutre nodes are the xml nodes that define the hierarchical structure of
# the bill.
STRUCTURE_NODES = [
    "division",
    "subdivision",
    "title",
    "subtitle",
    "section",
    "subsection",
    "paragraph",
    "subparagraph",
    "clause",
    "subclause",
    "item",
    "subitem",
]


def pretty_print(text, width=80):
    """
    This looks like a bouqitue pprint I wrote for redlining. Bringing it over
    for now. Prints the specified text with a maximum line width of the
    specified width.

    Args:
        text (str): The text to print. width (int, optional): The maximum line
        width. Defaults to 80.
    """
    wrapper = textwrap.TextWrapper(width=width)
    paragraphs = text.split("\n\n")  # Split text into paragraphs

    for paragraph in paragraphs:
        wrapped_text = wrapper.fill(paragraph)
        print(wrapped_text)
        print()  # Print an empty line between paragraphs


def clean_text(text: str) -> str:
    """
    Cleans the specified text by removing extra whitespace around parentheses.

    Args:
        text (str): The text to clean.

    Returns:
        str: The cleaned text.
    """
    text = re.sub(r"\s+", " ", text)  # - removes excess spaces
    # - removes spaces trailing open parentheses
    text = re.sub(r"\s+\)", ")", text)
    # - removes spaces preceding close parentheses
    text = re.sub(r"\(\s+", "(", text)
    return text


def modify_quoted_blocks(root):
    """
    Modifies the specified XML tree by adding '-within-quoted-block' to the tag
    names of structure nodes within quoted blocks.

    Args:
        root (Element): The root element of the XML tree.

    Returns:
        Element: The modified XML tree.
    """
    for node in root.iter():
        if node.tag == "quoted-block":
            structure_children = [
                child for child in node.iter() if child.tag in STRUCTURE_NODES
            ]
            for child in structure_children:
                child.tag = child.tag + "-within-quoted-block"
        if node.tag == "-within-quoted-block":
            continue
    return root


def is_nested(node):
    """
    Determines whether the specified XML node is nested by checking if it has
    any child structure nodes.

    Args:
        node (Element): The XML node to check.

    Returns:
        bool: True if the node is nested, False otherwise.
    """
    # Nested flag defautl false
    nested = False

    # For each child of the node
    for child in node.iter():
        # skip the node itself
        if child == node:
            continue
        # if the child is a structure node, then the node is nested, and we can
        # break
        if child.tag in STRUCTURE_NODES:
            nested = True
            break
        else:
            continue
    return nested


def get_parent_structure_node(node):
    """
    Returns the first parent structure node of the specified XML node.

    Args:
        node (Element): The XML node to get the parent structure node of.

    Returns:
        Element: The first parent structure node of the specified XML node.
    """
    # Get first parent
    parent_structure_node = node.getparent()

    # Continue to get parent until the parent is a structure node
    while parent_structure_node.tag not in STRUCTURE_NODES:
        parent_structure_node = parent_structure_node.getparent()
    return parent_structure_node


def get_non_structure_text(node) -> str:
    """
    Returns the non-structure text of the specified XML node.

    Args:
        node (Element): The XML node to get the non-structure text of.

    Returns:
        str: The non-structure text of the specified XML node.
    """
    # initialize text
    text = ""

    # for direct children of the node
    for child in node:

        # if child is structure node, skip it
        if child.tag in STRUCTURE_NODES:
            continue

        # else, get all the text
        else:
            text += get_text(child)

    return text


def is_descendant(node, tag):
    """
    Determines whether the specified XML node is a descendant of the specified
    tag.

    Args:
        node (Element): The XML node to check. tag (str): The tag to check if
        the node is a descendant of.

    Returns:
        bool: True if the node is a descendant of the tag, False otherwise.
    """
    if node.tag == tag:
        return True
    if node.getparent() is not None:
        return is_descendant(node.getparent(), tag)
    return False


def get_text(node) -> str:
    """
    Returns the text content of the specified XML node, with special handling
    for quote and quoted-block nodes.

    Args:
        node (Element): The XML node to get the text content of.

    Returns:
        str: The text content of the specified XML node.
    """
    text = ""
    qid = 1

    quote_nodes = list(node.iter("quote"))  # Get a list of all quote nodes
    # last_quote_node = quote_nodes[-1] if quote_nodes else None

    for child in node.iter():

        # process quoted-block nodes and their descendants
        if child.tag == "quoted-block":
            text += f"<quoted-block-{qid}>"
            qid += 1
            text += child.tail if child.tail else ""
            continue

        if is_descendant(child, "quoted-block"):
            continue

        # process quote nodes and skip their descendants
        if child.tag == "quote":
            text += f"<quote-{qid}>"
            qid += 1
            # add tail only if quote node is not the last quote node if child !=
            # last_quote_node:
            text += child.tail if child.tail else ""
            continue

        if is_descendant(child, "quote"):
            continue

        # replace enum nodes with a special character
        if child.tag == "enum":
            text += "<enum>"
            text += child.tail if child.tail else ""
            continue

        # get text and tail content of other nodes
        else:
            text += " " + child.text if child.text else ""
            text += " " + child.tail if child.tail else ""

    return text


def process_node(node) -> str:
    """
    Processes the specified XML node by getting the text content of its parent
    structure node, cleaning the text, and returning it.

    Args:
        node (Element): The XML node to process.

    Returns:
        str: The cleaned text content of the parent structure node of the
        specified XML node.
    """
    # Get the parent structure node to which we belong
    parent_structure_node = get_parent_structure_node(node)

    # Get text in that parent structure node
    text = get_text(parent_structure_node)

    # Clean the text and return it
    text = clean_text(text)
    return text


def process_node_recursive(
    node,
    inherited_text: str,
    accumulator: dict,
    verbose: bool = False,
    initial_call: bool = True,
):
    """
    Recursively processes the specified XML node and its descendants,
    accumulating text content in a dictionary.

    Args:
        node (Element): The XML node to process.
        inherited_text (str): The text content inherited from the parent node. accumulator (dict): The
        dictionary to accumulate text content in.
        verbose (bool, optional): Whether to print verbose output. Defaults to False.
        initial_call (bool, optional): Whether this is the initial call to the function. Defaults to True.

    Returns:
        dict: The dictionary containing the accumulated text content.
    """
    if verbose:
        pretty_print("starting a potentially recursive process")
        pretty_print(f"node: {node.tag}")
        pretty_print(f"inherited text: {clean_text(inherited_text)}")

    # We need to determine whether the node is nested or not.
    nested = is_nested(node)

    # If the node is nested, then we need to recurse
    if nested:
        for child in node:

            if child.tag in STRUCTURE_NODES:
                # if it's a structure node, then we need to pass along the
                # structure child with modified inherited text. The inherited
                # text at this point should be whatever we've gotten thus far in
                # the recursion + the non-structure text of the current node
                new_inheritance = get_non_structure_text(node)

                if verbose:
                    pretty_print(f"conditionally recursing on {child.tag}")
                    pretty_print(
                        f"new inherited text: {clean_text(inherited_text + new_inheritance)}"
                    )
                process_node_recursive(
                    child,
                    inherited_text + new_inheritance,
                    accumulator,
                    verbose,
                    initial_call=False,
                )

    # If the node is not nested, then we need to process it
    else:
        if verbose:
            pretty_print("No further recursion needed. Processing node:")
            pretty_print(f"node: {node.tag}")
            pretty_print(f'id: {node.get("id")}')
            pretty_print(f"Initial call? {initial_call}")

        # Get the text of the node
        text = get_text(node)

        # We still need to concatenate the inherited text
        text = inherited_text + text

        # clean up the text
        text = clean_text(text)

        # get id attribute of node
        key = node.get("id")

        accumulator[key] = text

    # Return the accumulator
    return accumulator


# IF I EVER WANT TO EXTRACT AMENDATORY INSTRUCTIONS IN PARTICULAR, THESE ARE
# FUNCTIONS THAT MIGHT BE USEFUL.
#
#
#
def get_instructions(root, max_count=None, verbose: bool = False):
    """
    Extracts instructions from the specified XML root element.

    Args:
        root (Element): The XML root element to extract instructions from.
        max_count (int, optional): The maximum number of nodes to process.
        Defaults to None. verbose (bool, optional): Whether to print verbose
        output. Defaults to False.

    Returns:
        dict: A dictionary of instructions, where the keys are the IDs of the
        structure nodes containing the instructions, and the values are the text
        content of the instructions.
    """
    instructions = {}
    count = 0

    for node in root.iter():

        node_text = node.text if node.text else ""
        node_tail = node.tail if node.tail else ""

        full_node_text = " ".join([node_text, node_tail])
        full_node_text = clean_text(full_node_text)

        if "is amended" in full_node_text:

            count += 1

            parent_structure_node = get_parent_structure_node(node)
            nested = is_nested(parent_structure_node)

            if not nested:
                text = process_node(node)
                key = parent_structure_node.get("id")
                instructions[key] = text

            else:
                parent_text = get_non_structure_text(parent_structure_node)
                acc = {}
                for child in parent_structure_node:
                    if child.tag in STRUCTURE_NODES:
                        acc = process_node_recursive(
                            child, parent_text, acc, verbose)
                instructions.update(acc)

            if verbose:
                pretty_print(f"count: {count}")
                pretty_print("=====================")

            if max_count is not None and count == max_count:

                break

    return instructions


def transform_instruction(node) -> dict:
    """
    Transforms the specified XML node into a dictionary.

    Args:
        node (Element): The XML node to transform.

    Returns:
        dict: A dictionary representation of the specified XML node.
    """
    # Initialize the dictionary that will be returned.
    d = {
        "type": node.tag,
        "id": node.get("id"),
        "content": [],
        "fullTextContent": "",
        "children": [],
    }

    ### PROCESS ###
    # This is looping over the top-level children of the node.
    for child in node:

        # If the child is a structure node, recurse on it.
        if child.tag in STRUCTURE_NODES:
            d["children"].append(transform_instruction(child))
            continue

        # start process the node itself
        d["content"].append({"type": child.tag, "content": child.text})

        # If child has children, and we've determined it's not a structure node,
        # process them. The phenomenon we're capturing here is generally
        # something like: <text> Some text that is interspersed with a
        #   <external-xref> citation</external-xref> and some more text, and
        #   also a <quote> quote or two, </quote> and we want to be mindful of
        # the tail content as well. </text>
        if len(child) > 0:
            # For each subchild
            for subchild in child:

                # Append text
                d["content"].append(
                    {"type": subchild.tag, "content": subchild.text})

                # If it has a tail that is not none, append it as well
                if subchild.tail is not None:
                    d["content"].append(
                        {"type": "tail", "content": subchild.tail})

        # if the child had a tail add it to the content
        if child.tail is not None:
            d["content"].append({"type": "tail", "content": child.tail})

    # If the node had a tail, add it to the content
    if node.tail is not None:
        if node.tail != "\n":
            d["content"].append({"type": "tail", "content": node.tail})

    # drop newline content
    d["content"] = [
        item
        for item in d["content"]
        if item["content"] is not None and item["content"].strip() != ""
    ]

    # Having processed the node, we can set the fullTextContent value by
    # iterating through the content array
    d["fullTextContent"] = "".join(
        [c["content"] for c in d["content"] if c["content"] is not None]
    )
    return d
