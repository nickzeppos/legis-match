import requests
from lxml import etree as et


def fetch_bill(congress_number: int, bill_number: int, bill_type: str, bill_version: str):

    # Construct URL based on input parameters
    url = "https://www.govinfo.gov/content/pkg/BILLS-" + str(congress_number) + bill_type + str(bill_number) + \
        str(bill_version) + "/xml/BILLS-" + str(congress_number) + \
        bill_type + str(bill_number) + str(bill_version) + ".xml"

    # Use URL to perform request, store file as response, convert to ETree object, get root of tree
    response = requests.get(url)
    return response.content


def write_bill_xml(bill, congress_number: int, bill_number: int, bill_type: str, bill_version: str):
    file_path = f'data/{congress_number}{bill_type}{bill_number}{bill_version}.xml'
    with open(file_path, 'wb') as f:
        f.write(bill)


def get_bill_xml(congress_number: int, bill_number: int, bill_type: str, bill_version: str):
    file_path = f'data/{congress_number}{bill_type}{bill_number}{bill_version}.xml'
    with open(file_path, 'r') as f:
        return f.read()


def get_core_bill_xml(congress_number: int, bill_number: int, bill_type: str, bill_version: str):
    parser = et.XMLParser()
    xml = get_bill_xml(congress_number, bill_number,
                       bill_type, bill_version)
    parsed = et.ElementTree(et.fromstring(xml, parser))
    return parsed.find('.//legis-body')
