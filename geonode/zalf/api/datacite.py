import json
import logging
import re
import base64

import requests as _requests

from django.conf import settings
from django.core.exceptions import ValidationError

from lxml import etree

logger = logging.getLogger(__name__)

# DataCite REST API endpoint path
DATACITE_DOIS_PATH = "dois"

# DataCite XML namespace
DATACITE_NS = "http://datacite.org/schema/kernel-4"
DATACITE_NSMAP = {"datacite": DATACITE_NS}


def validate_doi_prefix(prefix):
    """
    Validate that a DOI prefix has the correct format (e.g., '10.12345').

    DOI prefixes must start with '10.' followed by at least one digit.
    """
    if not prefix:
        raise ValidationError("DOI prefix is required")

    pattern = r"^10\.\d{4,}$"
    if not re.match(pattern, prefix):
        raise ValidationError(
            f"Invalid DOI prefix format: '{prefix}'. "
            "Expected format: '10.XXXXX' (e.g., '10.12345')"
        )
    return True


def _get_catalogue_backend():
    """Get the active catalogue backend instance."""
    from geonode.catalogue import get_catalogue
    return get_catalogue()


def get_datacite_xml(resource):
    """
    Get DataCite XML metadata for a GeoNode resource via pycsw's
    DataCite output schema plugin.

    Args:
        resource: A GeoNode ResourceBase instance

    Returns:
        str: DataCite XML string, or None if unavailable
    """
    catalogue = _get_catalogue_backend()

    if hasattr(catalogue, 'get_datacite_record'):
        return catalogue.get_datacite_record(resource.uuid)

    logger.warning(
        "Catalogue backend does not support get_datacite_record. "
        "DataCite XML generation is only supported with pycsw_local backend."
    )
    return None


def _patch_xml_doi(datacite_xml, doi):
    """
    Replace the <identifier identifierType="DOI"> value inside a DataCite XML
    document with the given DOI string.

    This is necessary when the XML was generated for a different DOI (e.g. using
    the resource UUID as suffix) but we are registering a shared collection DOI.

    Returns the patched XML as a UTF-8 string.
    """
    try:
        xml_bytes = datacite_xml.encode("utf-8") if isinstance(datacite_xml, str) else datacite_xml
        root = etree.fromstring(xml_bytes)

        # DataCite XML uses a namespace; find the identifier element
        ns = {"dc": DATACITE_NS}
        identifier_el = root.find("dc:identifier", ns)
        if identifier_el is not None:
            identifier_el.text = doi
        else:
            # Element absent – create it
            identifier_el = etree.SubElement(root, f"{{{DATACITE_NS}}}identifier")
            identifier_el.set("identifierType", "DOI")
            identifier_el.text = doi

        return etree.tostring(root, encoding="unicode", xml_declaration=False)
    except etree.XMLSyntaxError as e:
        logger.warning(f"Could not patch DOI in DataCite XML: {e}")
        return datacite_xml if isinstance(datacite_xml, str) else datacite_xml.decode("utf-8")


def build_datacite_payload(resource, doi_prefix, doi_suffix=None, event="publish"):
    """
    Build the JSON:API payload for the DataCite REST API.

    When DataCite XML is available (via pycsw) it is base64-encoded and sent in
    the ``xml`` attribute.  In that case only ``doi``, ``event``, ``url``, and
    ``xml`` are included – ``prefix`` and ``suffix`` are read-only response
    fields and must not be sent in a POST request.

    When no XML is available a minimal JSON metadata fallback is used instead.

    Args:
        resource: A GeoNode ResourceBase instance
        doi_prefix: The DOI prefix (e.g., '10.12345')
        doi_suffix: Optional DOI suffix (defaults to resource UUID)
        event: DataCite event ('publish', 'register', or 'hide')

    Returns:
        dict: JSON:API payload ready for POST to DataCite API
    """
    if doi_suffix is None:
        doi_suffix = str(resource.uuid)

    doi = f"{doi_prefix}/{doi_suffix}"

    # Landing page URL
    site_url = settings.SITEURL.rstrip("/")
    url = f"{site_url}/catalogue/#/dataset/{resource.uuid}"

    # Try to obtain DataCite XML from pycsw
    datacite_xml = get_datacite_xml(resource)

    if datacite_xml:
        # Patch the <identifier> inside the XML to match the DOI we are
        # registering (pycsw may have generated it with a different suffix).
        patched_xml = _patch_xml_doi(datacite_xml, doi)
        xml_bytes = patched_xml.encode("utf-8")

        # When supplying XML the DataCite API only needs doi, event, url, xml.
        attributes = {
            "doi": doi,
            "event": event,
            "url": url,
            "xml": base64.b64encode(xml_bytes).decode("ascii"),
        }
    else:
        # TODO CONTINUE: HERE, THE CODE IS TRYING TO ACCESS DATACITE METADATA FROM MAP WHICH IS NOT AVAILABLE, BECAUSE THE MAP I
        # Fallback: build minimal JSON metadata attributes from the resource model.
        logger.warning(f"No DataCite XML available for resource {resource.uuid}, using JSON fallback")
        attributes = {
            "doi": doi,
            "event": event,
            "url": url,
        }
        attributes.update(_build_fallback_attributes(resource))

    payload = {
        "data": {
            "type": "dois",
            "attributes": attributes,
        }
    }

    return payload


def _build_fallback_attributes(resource):
    """
    Build minimal DataCite attributes directly from a GeoNode ResourceBase
    when pycsw DataCite XML is not available.
    """
    from datetime import datetime

    attributes = {
        "titles": [{"title": resource.title or "Untitled"}],
        "creators": [{"name": str(resource.owner) if resource.owner else "Unknown"}],
        "publisher": settings.ZALF_DATACITE_AGENT,
        "publicationYear": resource.date.year if resource.date else datetime.now().year,
        "types": {
            "resourceTypeGeneral": "Dataset",
            "resourceType": resource.resource_type or "Dataset",
        },
    }

    if resource.abstract:
        attributes["descriptions"] = [{
            "description": resource.abstract,
            "descriptionType": "Abstract",
        }]

    return attributes


def register_doi(resource, doi_prefix, doi_suffix=None, event="publish"):
    """
    Register a DOI for a GeoNode resource via the DataCite REST API.

    Args:
        resource: A GeoNode ResourceBase instance
        doi_prefix: The DOI prefix (e.g., '10.12345')
        doi_suffix: Optional DOI suffix (defaults to resource UUID)
        event: DataCite event ('publish', 'register', or 'hide')

    Returns:
        str: The registered DOI string (e.g., '10.12345/uuid-here')

    Raises:
        ValidationError: If DOI registration fails
    """
    validate_doi_prefix(doi_prefix)

    doi_url = settings.ZALF_DATACITE_BASE_URL.rstrip("/")
    doi_username = settings.ZALF_DATACITE_USERNAME
    doi_password = settings.ZALF_DATACITE_PASSWORD

    if not doi_username or not doi_password:
        raise ValidationError("DataCite credentials are not configured")

    payload = build_datacite_payload(resource, doi_prefix, doi_suffix=doi_suffix, event=event)
    doi = payload["data"]["attributes"]["doi"]

    logger.info(f"Registering DOI '{doi}' for resource '{resource.title}' (UUID: {resource.uuid})")

    # Build authorization header (Basic auth)
    credentials = base64.b64encode(f"{doi_username}:{doi_password}".encode()).decode()
    headers = {
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Basic {credentials}",
    }

    url = f"{doi_url}/{DATACITE_DOIS_PATH}"
    data = json.dumps(payload).encode("utf-8")

    # Log the outgoing payload (mask xml value to keep logs readable)
    debug_payload = json.loads(data)
    if "xml" in debug_payload.get("data", {}).get("attributes", {}):
        debug_payload["data"]["attributes"]["xml"] = "<base64-encoded XML omitted>"
    logger.debug(f"DataCite POST {url} payload: {json.dumps(debug_payload, indent=2)}")

    # Use requests directly — geonode's http_client evaluates `if response:`
    # which is False for 4xx/5xx, silently discarding the response body.
    try:
        response = _requests.post(
            url,
            data=data,
            headers=headers,
            timeout=30,
            verify=True,
        )
    except _requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to DataCite API at {url}: {e}")
        raise ValidationError(f"Failed to connect to DataCite API: {e}")

    if response.status_code in (200, 201):
        # Success - update the resource's DOI field
        try:
            registered_doi = response.json().get("data", {}).get("attributes", {}).get("doi", doi)
        except (json.JSONDecodeError, ValueError):
            registered_doi = doi

        resource.doi = registered_doi
        resource.save(update_fields=["doi"])

        logger.info(f"Successfully registered DOI '{registered_doi}' for resource '{resource.title}'")
        return registered_doi
    else:
        error_msg = f"DataCite API returned status {response.status_code}"
        try:
            error_data = response.json()
            if isinstance(error_data, dict):
                errors = error_data.get("errors", [])
                if errors:
                    error_details = "; ".join(
                        f"{e.get('title', '')} – {e.get('detail', '')}".strip(" –")
                        for e in errors
                    )
                    error_msg += f": {error_details}"
        except (json.JSONDecodeError, ValueError):
            pass

        # Always log the full raw response body so the DataCite error is visible
        logger.error(f"DOI registration failed: {error_msg}")
        logger.error(f"DataCite raw response body: {response.text}")
        raise ValidationError(error_msg)
