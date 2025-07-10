#!/usr/bin/env python3

# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "requests",
#     "tiktoken",
#     "defusedxml",
# ]
# ///

"""Standalone script to fetch and clean full text from PubMed/PMC given a PMID."""

import logging
import sys
from typing import Any

import requests
import tiktoken
from defusedxml import ElementTree

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleWebClient:
    """Simple web client for making HTTP requests."""

    def get(self, url: str, content_type: str = "xml", url_extra: str | None = None) -> Any:
        """Make a GET request and parse the response."""
        if url_extra:
            url += url_extra

        response = requests.get(url)
        response.raise_for_status()

        if content_type == "xml":
            return ElementTree.fromstring(response.text)
        elif content_type == "json":
            return response.json()
        else:
            return response.text


class NcbiClient:
    """Client for fetching paper data from NCBI."""

    EUTILS_HOST = "https://eutils.ncbi.nlm.nih.gov"
    EUTILS_FETCH_URL = "/entrez/eutils/efetch.fcgi?db={db}&id={id}&retmode={retmode}&rettype={rettype}&tool=standalone"
    PMCOA_GET_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"
    BIOC_GET_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/{pmcid}/ascii"

    def __init__(self):
        self.web_client = SimpleWebClient()

    def fetch_paper_metadata(self, pmid: str) -> dict[str, Any] | None:
        """Fetch basic paper metadata from PubMed."""
        url = self.EUTILS_FETCH_URL.format(db="pubmed", id=pmid, retmode="xml", rettype="abstract")
        full_url = f"{self.EUTILS_HOST}{url}"

        try:
            root = self.web_client.get(full_url, content_type="xml")
        except Exception as e:
            logger.error(f"Failed to fetch metadata for PMID {pmid}: {e}")
            return None

        # Find the article element
        article = root.find(f"PubmedArticle/MedlineCitation/PMID[.='{pmid}']/../..")
        if article is None:
            logger.error(f"No article found for PMID {pmid}")
            return None

        # Extract PMCID
        pmcid_elem = article.find("./PubmedData/ArticleIdList/ArticleId[@IdType='pmc']")
        pmcid = pmcid_elem.text if pmcid_elem is not None else None

        return {"pmid": pmid, "pmcid": pmcid}

    def check_pmc_availability(self, pmcid: str) -> bool:
        """Check if the paper is available in PMC."""
        if not pmcid:
            return False

        try:
            root = self.web_client.get(self.PMCOA_GET_URL.format(pmcid=pmcid), content_type="xml")
        except Exception as e:
            logger.error(f"Failed to check access for PMCID {pmcid}: {e}")
            return False

        # Look for a record with the given pmcid
        record = root.find(f"records/record[@id='{pmcid}']")

        if record is None:
            # Check for error
            err = root.find("error")
            if err is not None:
                err_code = err.attrib.get("code")
                logger.info(f"Paper not available in PMC for {pmcid}: {err_code}")
            return False

        # Print license
        license = record.attrib.get("license", "unknown")
        logger.info(f"Paper {pmcid} has license: {license}")

        return True

    def fetch_fulltext_xml(self, pmcid: str) -> str | None:
        """Fetch the full text XML from PMC BioC."""
        try:
            root = self.web_client.get(self.BIOC_GET_URL.format(pmcid=pmcid), content_type="xml")
        except Exception as e:
            logger.error(f"Failed to fetch full text for PMCID {pmcid}: {e}")
            return None

        # Find the document
        doc = root.find(f"./document[id='{pmcid.upper().lstrip('PMC')}']")
        if doc is None:
            # Try with original pmcid
            doc = root.find(f"./document[id='{pmcid.upper()}']")

        if doc is None:
            logger.error(f"Document not found in BioC response for {pmcid}")
            return None

        return ElementTree.tostring(doc, encoding="unicode")


def extract_text_from_xml(xml_doc: str) -> str:
    """Extract and clean text from BioC XML document."""
    if not xml_doc:
        return ""

    # Parse the XML
    root = ElementTree.fromstring(xml_doc)

    # Collect all text sections
    texts = []

    # Iterate through all passages
    for passage in root.iterfind("./passage"):
        # Get section type
        section_type = passage.findtext("infon[@key='section_type']")
        if not section_type:
            continue

        # Get the text content
        text_elem = passage.find("text")
        if text_elem is not None and text_elem.text:
            # Clean the text: remove newlines and extra whitespace
            cleaned_text = " ".join(text_elem.text.strip().split())
            if cleaned_text:
                texts.append(cleaned_text)

    # Join all sections with newlines
    return "\n".join(texts)


def fetch_and_clean_fulltext(pmid: str) -> str | None:
    """Main function to fetch and clean full text given a PMID."""
    client = NcbiClient()

    # Step 1: Get paper metadata including PMCID
    logger.info(f"Fetching metadata for PMID {pmid}...")
    metadata = client.fetch_paper_metadata(pmid)
    if not metadata:
        logger.error("Failed to fetch paper metadata")
        return None

    pmcid = metadata.get("pmcid")
    if not pmcid:
        logger.error("No PMCID found for this paper - full text not available in PMC")
        return None

    logger.info(f"Found PMCID: {pmcid}")

    # Step 2: Check if the paper is available in PMC
    logger.info("Checking PMC availability...")
    if not client.check_pmc_availability(pmcid):
        logger.error("Paper is not available in PMC")
        return None

    # Step 3: Fetch the full text XML
    logger.info("Fetching full text XML...")
    xml_doc = client.fetch_fulltext_xml(pmcid)
    if not xml_doc:
        logger.error("Failed to fetch full text XML")
        return None

    # Step 4: Extract and clean the text
    logger.info("Extracting and cleaning text...")
    fulltext = extract_text_from_xml(xml_doc)

    # Log token count
    encoding = tiktoken.get_encoding("cl100k_base")  # Standard encoding for GPT-4 and newer models
    token_count = len(encoding.encode(fulltext))
    logger.info(f"Full text token count: {token_count:,}")

    return fulltext


def main():
    """Command line interface."""
    if len(sys.argv) < 2:
        print("Usage: python fetch_fulltext.py <PMID>")
        print("Example: python fetch_fulltext.py 12345678")
        sys.exit(1)

    pmid = sys.argv[1]

    # Fetch and print the full text
    fulltext = fetch_and_clean_fulltext(pmid)

    if fulltext:
        print(fulltext)
    else:
        print(f"Failed to retrieve full text for PMID {pmid}")
        sys.exit(1)


if __name__ == "__main__":
    main()
