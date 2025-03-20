"""
Functions for transforming meaningful queries w/r/t bill structure into xml extractions.
"""


def get_section(bill_xml, section_number):
    """
    Get a section from a bill xml by section number
    """
    section = None
    for node in bill_xml.iter():
        if node.tag == "section":
            # first enum is ection number
            enum = node.find("enum").text
            # enum comes in as "1.", so remove punctuation to check
            enum = enum.replace(".", "")
            if enum == section_number:
                section = node
                break
    if section is None:
        raise ValueError(f"Section {section_number} not found in bill xml")
    return section


def get_all_sections(bill_xml):
    """
    Get all sections from a bill xml, returned as a dictionary of section number to section xml.
    """
    sections = {}
    for node in bill_xml.iter():
        if node.tag == "section":
            enum = node.find("enum").text
            # enum comes in as "1.", so remove punctuation to check
            enum = enum.replace(".", "")
            sections[enum] = node
    return sections
