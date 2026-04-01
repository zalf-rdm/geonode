import json
import logging
import re
import base64

import requests as _requests

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from lxml import etree

logger = logging.getLogger(__name__)

# DataCite REST API endpoint path
DATACITE_DOIS_PATH = "dois"

# DataCite XML namespace
DATACITE_NS = "http://datacite.org/schema/kernel-4"

# DataCite resolver base URLs
_DATACITE_PROD_API = "https://api.datacite.org"
_DATACITE_TEST_API = "https://api.test.datacite.org"
_DATACITE_PROD_RESOLVER = "https://doi.org"
_DATACITE_TEST_RESOLVER = "https://handle.test.datacite.org"

# Cache TTL for DataCite prefix lookups (seconds).  Prefixes change rarely.
_DATACITE_PREFIX_CACHE_TTL = 3600


def doi_resolver_base_url():
    """
    Return the correct DOI resolver base URL depending on whether the
    configured DataCite API endpoint is production or test.

    - Production API (api.datacite.org)      → https://doi.org
    - Test API      (api.test.datacite.org)  → https://handle.test.datacite.org
    """
    base = getattr(settings, "ZALF_DATACITE_BASE_URL", _DATACITE_PROD_API).rstrip("/")
    if "test" in base:
        return _DATACITE_TEST_RESOLVER
    return _DATACITE_PROD_RESOLVER


def doi_to_fqdn(doi):
    """Convert a bare DOI (e.g. '10.20387/abc') to a fully-qualified URL."""
    if doi and doi.startswith("https://"):
        return doi
    return f"{doi_resolver_base_url()}/{doi}"


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
            f"Invalid DOI prefix format: '{prefix}'. " "Expected format: '10.XXXXX' (e.g., '10.12345')"
        )
    return True


# ---------------------------------------------------------------------------
# DataCite account helpers
# ---------------------------------------------------------------------------


def get_datacite_accounts():
    """Return the full list of configured DataCite accounts."""
    return getattr(settings, "ZALF_DATACITE_ACCOUNTS", [])


def get_datacite_accounts_for_user(user):
    """
    Return the DataCite accounts the given user may use.

    Superusers get all accounts.  Other users get accounts whose ``groups``
    list contains at least one Django group the user belongs to.
    """
    accounts = get_datacite_accounts()
    if user.is_superuser:
        return accounts
    user_groups = set(user.groups.values_list("name", flat=True))
    return [acct for acct in accounts if user_groups & set(acct.get("groups", []))]


def fetch_prefixes_for_account(account):
    """
    Fetch the DOI prefixes associated with a DataCite repository account.

    Uses ``GET /clients/{client-id}`` (JSON:API) and reads
    ``data.relationships.prefixes.data``.  The dedicated sub-endpoint
    ``/clients/{id}/relationships/prefixes`` is not used because it returns
    an empty list for some accounts even when prefixes are assigned.
    Results are cached using Django's cache framework to avoid hammering the
    DataCite API on every request.

    Args:
        account (dict): Account dict with ``username`` and ``password`` keys.

    Returns:
        list[str]: DOI prefix strings (e.g. ``["10.20387", "10.99999"]``).
                   Returns an empty list on any error so callers degrade
                   gracefully when the DataCite API is unreachable.
    """
    username = account.get("username", "")
    password = account.get("password", "")
    if not username:
        return []

    cache_key = f"datacite_prefixes_{username}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    base_url = getattr(settings, "ZALF_DATACITE_BASE_URL", _DATACITE_PROD_API).rstrip("/")
    # The client ID is the lowercase username in the DataCite API
    client_id = username.lower()
    # Use GET /clients/{id} and read relationships.prefixes — the dedicated
    # /clients/{id}/relationships/prefixes sub-endpoint returns empty data
    # for some accounts even when prefixes exist.
    url = f"{base_url}/clients/{client_id}"

    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {
        "Accept": "application/vnd.api+json",
        "Authorization": f"Basic {credentials}",
    }

    try:
        response = _requests.get(url, headers=headers, timeout=15, verify=True)
    except _requests.exceptions.RequestException as e:
        logger.warning(f"Could not fetch DataCite prefixes for '{username}': {e}")
        return []

    if response.status_code != 200:
        logger.warning(
            f"DataCite prefix fetch for '{username}' returned HTTP {response.status_code}: {response.text[:200]}"
        )
        return []

    try:
        relationships = response.json().get("data", {}).get("relationships", {})
        prefix_items = relationships.get("prefixes", {}).get("data", [])
        prefixes = [item["id"] for item in prefix_items if item.get("id")]
    except (ValueError, KeyError, TypeError) as e:
        logger.warning(f"Unexpected DataCite client response for '{username}': {e}")
        prefixes = []

    cache.set(cache_key, prefixes, _DATACITE_PREFIX_CACHE_TTL)
    logger.debug(f"DataCite prefixes for '{username}': {prefixes}")
    return prefixes


def get_doi_prefixes_for_user(user):
    """
    Return a deduplicated, sorted list of DOI prefix strings the user may use.

    Prefixes are fetched from the DataCite API for each account the user has
    access to.  Results are cached per account (see ``fetch_prefixes_for_account``).
    """
    seen = set()
    for acct in get_datacite_accounts_for_user(user):
        for prefix in fetch_prefixes_for_account(acct):
            seen.add(prefix)
    return sorted(seen)


def get_datacite_account_for_prefix(doi_prefix, user=None):
    """
    Return the first DataCite account that has access to the given prefix.

    If *user* is provided, only accounts the user may use are considered
    (accounts whose groups overlap with the user's groups, or all accounts
    if the user is a superuser).

    The prefix list for each candidate account is fetched from the DataCite
    API (cached).

    Raises ``ValidationError`` if no matching account is found.
    """
    accounts = get_datacite_accounts_for_user(user) if user else get_datacite_accounts()
    for acct in accounts:
        if doi_prefix in fetch_prefixes_for_account(acct):
            return acct
    raise ValidationError(
        f"No DataCite account found for prefix '{doi_prefix}'" + (f" accessible by user '{user}'" if user else "")
    )


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

    if hasattr(catalogue, "get_datacite_record"):
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
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml_bytes, parser)

        # DataCite XML uses a namespace; find the identifier element
        ns = {"dc": DATACITE_NS}
        identifier_el = root.find("dc:identifier", ns)
        if identifier_el is None:
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

    # Landing page URL — use the resource's own absolute URL so the correct
    # resource type and pk are used (e.g. /catalogue/#/map/42 for maps,
    # /catalogue/#/tabular-collection/42 for collections, etc.)
    site_url = settings.SITEURL.rstrip("/")
    resource_path = (resource.get_absolute_url() or "").lstrip("/")
    url = f"{site_url}/{resource_path}"

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
        "publisher": getattr(settings, "ZALF_DATACITE_AGENT", ""),
        "publicationYear": resource.date.year if resource.date else datetime.now().year,
        "types": {
            "resourceTypeGeneral": "Dataset",
            "resourceType": resource.resource_type or "Dataset",
        },
    }

    if resource.abstract:
        attributes["descriptions"] = [
            {
                "description": resource.abstract,
                "descriptionType": "Abstract",
            }
        ]

    return attributes


def register_doi(resource, doi_prefix, doi_suffix=None, event="publish", user=None):
    """
    Register a DOI for a GeoNode resource via the DataCite REST API.

    Args:
        resource: A GeoNode ResourceBase instance
        doi_prefix: The DOI prefix (e.g., '10.12345')
        doi_suffix: Optional DOI suffix (defaults to resource UUID)
        event: DataCite event ('publish', 'register', or 'hide')
        user: The requesting user — used to resolve credentials from
              ``ZALF_DATACITE_ACCOUNTS``.  When ``None``, the first account
              matching the prefix is used (for backward compat / CLI use).

    Returns:
        str: The registered DOI as a fully-qualified URL

    Raises:
        ValidationError: If DOI registration fails
    """
    validate_doi_prefix(doi_prefix)

    account = get_datacite_account_for_prefix(doi_prefix, user=user)
    doi_username = account["username"]
    doi_password = account["password"]

    doi_url = settings.ZALF_DATACITE_BASE_URL.rstrip("/")

    if not doi_username or not doi_password:
        raise ValidationError("DataCite credentials are not configured")

    doi = f"{doi_prefix}/{doi_suffix if doi_suffix is not None else resource.uuid}"
    payload = build_datacite_payload(resource, doi_prefix, doi_suffix=doi_suffix, event=event)

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
        # Success - read the registered DOI from the response
        try:
            attrs = response.json().get("data", {}).get("attributes", {})
            # Prefer the full URL from the identifiers array (contains the
            # correct resolver for both prod and test environments).
            doi_identifier = next(
                (i.get("identifier") for i in attrs.get("identifiers", []) if i.get("identifierType") == "DOI"),
                None,
            )
            registered_doi = doi_identifier or doi_to_fqdn(attrs.get("doi", doi))
        except (ValueError, StopIteration):
            registered_doi = doi_to_fqdn(doi)

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
                        f"{e.get('title', '')} – {e.get('detail', '')}".strip(" –") for e in errors
                    )
                    error_msg += f": {error_details}"
        except ValueError:
            pass

        # Always log the full raw response body so the DataCite error is visible
        logger.error(f"DOI registration failed: {error_msg}")
        logger.error(f"DataCite raw response body: {response.text}")
        raise ValidationError(error_msg)
