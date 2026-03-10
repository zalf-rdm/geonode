"""
Unit tests for geonode.zalf.api.datacite — account helpers and prefix
resolution.  All external HTTP calls are patched out.
"""
import base64
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from geonode.zalf.api.datacite import (
    _build_fallback_attributes,
    _patch_xml_doi,
    build_datacite_payload,
    doi_resolver_base_url,
    doi_to_fqdn,
    fetch_prefixes_for_account,
    get_datacite_account_for_prefix,
    get_datacite_accounts_for_user,
    get_doi_prefixes_for_user,
    register_doi,
    validate_doi_prefix,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACCOUNTS = [
    {"username": "ORG.ALPHA", "password": "pw-alpha", "groups": ["alpha-team"]},
    {"username": "ORG.BETA",  "password": "pw-beta",  "groups": ["beta-team"]},
]

_SETTINGS = {
    "ZALF_DATACITE_BASE_URL": "https://api.datacite.org/",
    "ZALF_DATACITE_ACCOUNTS": _ACCOUNTS,
    "ZALF_DATACITE_AGENT": "Test Agent",
    "PUBLISH_DATA_COLLECTION_ALLOWED_GROUPS": ["alpha-team", "beta-team"],
}


def _make_client_response(prefixes):
    """Build a minimal DataCite GET /clients/{id} JSON:API response."""
    return {
        "data": {
            "id": "org.alpha",
            "type": "clients",
            "relationships": {
                "prefixes": {
                    "data": [{"id": p, "type": "prefixes"} for p in prefixes]
                }
            },
        }
    }


# ---------------------------------------------------------------------------
# validate_doi_prefix
# ---------------------------------------------------------------------------

class TestValidateDoiPrefix(TestCase):

    def test_valid_prefix(self):
        self.assertTrue(validate_doi_prefix("10.12345"))
        self.assertTrue(validate_doi_prefix("10.20387"))
        self.assertTrue(validate_doi_prefix("10.99999"))

    def test_too_short_digits(self):
        with self.assertRaises(ValidationError):
            validate_doi_prefix("10.123")   # only 3 digits

    def test_missing_10_dot(self):
        with self.assertRaises(ValidationError):
            validate_doi_prefix("11.12345")

    def test_empty(self):
        with self.assertRaises(ValidationError):
            validate_doi_prefix("")

    def test_none(self):
        with self.assertRaises(ValidationError):
            validate_doi_prefix(None)


# ---------------------------------------------------------------------------
# doi_resolver_base_url / doi_to_fqdn
# ---------------------------------------------------------------------------

class TestDoiHelpers(TestCase):

    @override_settings(ZALF_DATACITE_BASE_URL="https://api.datacite.org/")
    def test_prod_resolver(self):
        self.assertEqual(doi_resolver_base_url(), "https://doi.org")

    @override_settings(ZALF_DATACITE_BASE_URL="https://api.test.datacite.org/")
    def test_test_resolver(self):
        self.assertEqual(doi_resolver_base_url(), "https://handle.test.datacite.org")

    @override_settings(ZALF_DATACITE_BASE_URL="https://api.datacite.org/")
    def test_doi_to_fqdn_bare(self):
        self.assertEqual(doi_to_fqdn("10.20387/abc"), "https://doi.org/10.20387/abc")

    @override_settings(ZALF_DATACITE_BASE_URL="https://api.datacite.org/")
    def test_doi_to_fqdn_already_fqdn(self):
        fqdn = "https://doi.org/10.20387/abc"
        self.assertEqual(doi_to_fqdn(fqdn), fqdn)


# ---------------------------------------------------------------------------
# fetch_prefixes_for_account
# ---------------------------------------------------------------------------

@override_settings(**_SETTINGS)
class TestFetchPrefixesForAccount(TestCase):

    def setUp(self):
        # Ensure no stale cache entries between tests
        cache.clear()

    def _mock_response(self, prefixes, status_code=200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = _make_client_response(prefixes)
        mock_resp.text = ""
        return mock_resp

    @patch("geonode.zalf.api.datacite._requests.get")
    def test_returns_prefixes(self, mock_get):
        mock_get.return_value = self._mock_response(["10.20387", "10.99999"])
        result = fetch_prefixes_for_account(_ACCOUNTS[0])
        self.assertEqual(result, ["10.20387", "10.99999"])

    @patch("geonode.zalf.api.datacite._requests.get")
    def test_result_is_cached(self, mock_get):
        mock_get.return_value = self._mock_response(["10.20387"])
        fetch_prefixes_for_account(_ACCOUNTS[0])
        fetch_prefixes_for_account(_ACCOUNTS[0])
        # HTTP call must only happen once despite two invocations
        self.assertEqual(mock_get.call_count, 1)

    @patch("geonode.zalf.api.datacite._requests.get")
    def test_http_error_returns_empty(self, mock_get):
        mock_get.return_value = self._mock_response([], status_code=401)
        result = fetch_prefixes_for_account(_ACCOUNTS[0])
        self.assertEqual(result, [])

    @patch("geonode.zalf.api.datacite._requests.get")
    def test_connection_error_returns_empty(self, mock_get):
        import requests as _r
        mock_get.side_effect = _r.exceptions.ConnectionError("timeout")
        result = fetch_prefixes_for_account(_ACCOUNTS[0])
        self.assertEqual(result, [])

    @patch("geonode.zalf.api.datacite._requests.get")
    def test_uses_correct_auth_header(self, mock_get):
        mock_get.return_value = self._mock_response(["10.20387"])
        fetch_prefixes_for_account(_ACCOUNTS[0])
        _, kwargs = mock_get.call_args
        auth_header = kwargs["headers"]["Authorization"]
        expected = "Basic " + base64.b64encode(b"ORG.ALPHA:pw-alpha").decode()
        self.assertEqual(auth_header, expected)

    def test_missing_username_returns_empty(self):
        result = fetch_prefixes_for_account({"username": "", "password": "x"})
        self.assertEqual(result, [])

    @patch("geonode.zalf.api.datacite._requests.get")
    def test_malformed_json_response_returns_empty(self, mock_get):
        """If the API response JSON doesn't have the expected structure, return []"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": None}  # relationships key missing
        mock_get.return_value = mock_resp
        result = fetch_prefixes_for_account(_ACCOUNTS[0])
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# get_datacite_accounts_for_user
# ---------------------------------------------------------------------------

@override_settings(**_SETTINGS)
class TestGetAccountsForUser(TestCase):

    def _make_user(self, username, groups=(), is_superuser=False):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group as DjangoGroup
        User = get_user_model()
        user = User.objects.create_user(username=username, password="pw", is_superuser=is_superuser)
        for g in groups:
            grp, _ = DjangoGroup.objects.get_or_create(name=g)
            user.groups.add(grp)
        return user

    def test_superuser_gets_all_accounts(self):
        user = self._make_user("admin_user", is_superuser=True)
        accounts = get_datacite_accounts_for_user(user)
        self.assertEqual(len(accounts), 2)

    def test_group_member_gets_own_account(self):
        user = self._make_user("alpha_user", groups=["alpha-team"])
        accounts = get_datacite_accounts_for_user(user)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["username"], "ORG.ALPHA")

    def test_user_in_two_groups_gets_two_accounts(self):
        user = self._make_user("both_user", groups=["alpha-team", "beta-team"])
        accounts = get_datacite_accounts_for_user(user)
        self.assertEqual(len(accounts), 2)

    def test_unrelated_user_gets_no_accounts(self):
        user = self._make_user("outsider")
        accounts = get_datacite_accounts_for_user(user)
        self.assertEqual(accounts, [])


# ---------------------------------------------------------------------------
# get_doi_prefixes_for_user
# ---------------------------------------------------------------------------

@override_settings(**_SETTINGS)
class TestGetDoiPrefixesForUser(TestCase):

    def setUp(self):
        cache.clear()

    def _make_user(self, username, groups=()):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group as DjangoGroup
        User = get_user_model()
        user = User.objects.create_user(username=username, password="pw")
        for g in groups:
            grp, _ = DjangoGroup.objects.get_or_create(name=g)
            user.groups.add(grp)
        return user

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account")
    def test_returns_sorted_union(self, mock_fetch):
        mock_fetch.side_effect = lambda acct: (
            ["10.99999", "10.20387"] if acct["username"] == "ORG.ALPHA" else ["10.55555"]
        )
        user = self._make_user("both_user", groups=["alpha-team", "beta-team"])
        prefixes = get_doi_prefixes_for_user(user)
        self.assertEqual(prefixes, ["10.20387", "10.55555", "10.99999"])

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account")
    def test_no_accounts_returns_empty(self, mock_fetch):
        user = self._make_user("outsider")
        prefixes = get_doi_prefixes_for_user(user)
        self.assertEqual(prefixes, [])
        mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# get_datacite_account_for_prefix
# ---------------------------------------------------------------------------

@override_settings(**_SETTINGS)
class TestGetAccountForPrefix(TestCase):

    def setUp(self):
        cache.clear()

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account")
    def test_finds_correct_account(self, mock_fetch):
        mock_fetch.side_effect = lambda acct: (
            ["10.20387"] if acct["username"] == "ORG.ALPHA" else ["10.55555"]
        )
        acct = get_datacite_account_for_prefix("10.55555")
        self.assertEqual(acct["username"], "ORG.BETA")

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account")
    def test_raises_if_not_found(self, mock_fetch):
        mock_fetch.return_value = []
        with self.assertRaises(ValidationError):
            get_datacite_account_for_prefix("10.00000")

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account")
    def test_respects_user_scope(self, mock_fetch):
        """A user in only alpha-team cannot access a beta-team prefix."""
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group as DjangoGroup
        User = get_user_model()
        user = User.objects.create_user(username="alpha_only", password="pw")
        grp, _ = DjangoGroup.objects.get_or_create(name="alpha-team")
        user.groups.add(grp)

        mock_fetch.side_effect = lambda acct: (
            ["10.20387"] if acct["username"] == "ORG.ALPHA" else ["10.55555"]
        )
        # alpha-team prefix — OK
        acct = get_datacite_account_for_prefix("10.20387", user=user)
        self.assertEqual(acct["username"], "ORG.ALPHA")

        # beta-team prefix — should raise since this user only sees ORG.ALPHA
        with self.assertRaises(ValidationError):
            get_datacite_account_for_prefix("10.55555", user=user)


# ---------------------------------------------------------------------------
# _patch_xml_doi
# ---------------------------------------------------------------------------

_DATACITE_XML_WITH_ID = """\
<?xml version="1.0" encoding="UTF-8"?>
<resource xmlns="http://datacite.org/schema/kernel-4">
  <identifier identifierType="DOI">10.OLD/old-suffix</identifier>
  <titles><title>Test</title></titles>
</resource>"""

_DATACITE_XML_WITHOUT_ID = """\
<?xml version="1.0" encoding="UTF-8"?>
<resource xmlns="http://datacite.org/schema/kernel-4">
  <titles><title>Test</title></titles>
</resource>"""


class TestPatchXmlDoi(TestCase):

    def test_existing_identifier_is_replaced(self):
        result = _patch_xml_doi(_DATACITE_XML_WITH_ID, "10.20387/new-suffix")
        self.assertIn("10.20387/new-suffix", result)
        self.assertNotIn("10.OLD/old-suffix", result)

    def test_missing_identifier_element_is_created(self):
        result = _patch_xml_doi(_DATACITE_XML_WITHOUT_ID, "10.20387/new-suffix")
        self.assertIn("10.20387/new-suffix", result)

    def test_identifier_type_attribute_is_doi(self):
        from lxml import etree
        result = _patch_xml_doi(_DATACITE_XML_WITH_ID, "10.20387/x")
        root = etree.fromstring(result.encode())
        ns = {"dc": "http://datacite.org/schema/kernel-4"}
        el = root.find("dc:identifier", ns)
        self.assertEqual(el.get("identifierType"), "DOI")

    def test_malformed_xml_returns_original(self):
        bad_xml = "this is not xml <<<"
        result = _patch_xml_doi(bad_xml, "10.20387/x")
        self.assertEqual(result, bad_xml)

    def test_accepts_bytes_input(self):
        result = _patch_xml_doi(_DATACITE_XML_WITH_ID.encode("utf-8"), "10.20387/bytes")
        self.assertIn("10.20387/bytes", result)


# ---------------------------------------------------------------------------
# _build_fallback_attributes
# ---------------------------------------------------------------------------

class TestBuildFallbackAttributes(TestCase):

    def _make_resource(self, title="T", owner_str="Owner", abstract=None, date=None, resource_type="map"):
        resource = MagicMock()
        resource.title = title
        resource.owner = owner_str
        resource.abstract = abstract
        resource.date = date
        resource.resource_type = resource_type
        return resource

    def test_required_keys_present(self):
        attrs = _build_fallback_attributes(self._make_resource())
        for key in ("titles", "creators", "publisher", "publicationYear", "types"):
            self.assertIn(key, attrs)

    def test_title_used(self):
        attrs = _build_fallback_attributes(self._make_resource(title="My Map"))
        self.assertEqual(attrs["titles"][0]["title"], "My Map")

    def test_empty_title_becomes_untitled(self):
        attrs = _build_fallback_attributes(self._make_resource(title=""))
        self.assertEqual(attrs["titles"][0]["title"], "Untitled")

    def test_abstract_included_when_present(self):
        attrs = _build_fallback_attributes(self._make_resource(abstract="Some abstract"))
        self.assertIn("descriptions", attrs)
        self.assertEqual(attrs["descriptions"][0]["description"], "Some abstract")

    def test_abstract_omitted_when_none(self):
        attrs = _build_fallback_attributes(self._make_resource(abstract=None))
        self.assertNotIn("descriptions", attrs)

    def test_date_used_for_publication_year(self):
        import datetime
        attrs = _build_fallback_attributes(self._make_resource(date=datetime.date(2023, 6, 15)))
        self.assertEqual(attrs["publicationYear"], 2023)

    @override_settings(ZALF_DATACITE_AGENT="Test Agent")
    def test_publisher_comes_from_settings(self):
        attrs = _build_fallback_attributes(self._make_resource())
        self.assertEqual(attrs["publisher"], "Test Agent")


# ---------------------------------------------------------------------------
# build_datacite_payload
# ---------------------------------------------------------------------------

@override_settings(**_SETTINGS, SITEURL="https://example.org/")
class TestBuildDatacitePayload(TestCase):

    def _make_resource(self, uuid_val=None):
        import uuid as _uuid
        resource = MagicMock()
        resource.uuid = str(uuid_val or _uuid.uuid4())
        resource.title = "Test Resource"
        resource.owner = "test_owner"
        resource.abstract = None
        resource.date = None
        resource.resource_type = "map"
        resource.get_absolute_url.return_value = "/catalogue/#/map/1"
        return resource

    @patch("geonode.zalf.api.datacite.get_datacite_xml", return_value=None)
    def test_json_fallback_when_no_xml(self, mock_xml):
        resource = self._make_resource()
        payload = build_datacite_payload(resource, "10.20387", doi_suffix="test-suffix")
        attrs = payload["data"]["attributes"]
        self.assertEqual(attrs["doi"], "10.20387/test-suffix")
        self.assertEqual(attrs["event"], "publish")
        self.assertNotIn("xml", attrs)
        self.assertIn("titles", attrs)

    @patch("geonode.zalf.api.datacite.get_datacite_xml", return_value=_DATACITE_XML_WITH_ID)
    def test_xml_path_base64_encodes_xml(self, mock_xml):
        import base64 as _b64
        resource = self._make_resource()
        payload = build_datacite_payload(resource, "10.20387", doi_suffix="test-suffix")
        attrs = payload["data"]["attributes"]
        self.assertIn("xml", attrs)
        # Verify it decodes to something containing the patched DOI
        decoded = _b64.b64decode(attrs["xml"]).decode("utf-8")
        self.assertIn("10.20387/test-suffix", decoded)

    @patch("geonode.zalf.api.datacite.get_datacite_xml", return_value=None)
    def test_doi_suffix_defaults_to_resource_uuid(self, mock_xml):
        resource = self._make_resource(uuid_val="fixed-uuid-1234")
        payload = build_datacite_payload(resource, "10.20387")
        attrs = payload["data"]["attributes"]
        self.assertEqual(attrs["doi"], "10.20387/fixed-uuid-1234")

    @patch("geonode.zalf.api.datacite.get_datacite_xml", return_value=None)
    def test_url_built_from_siteurl_and_resource_path(self, mock_xml):
        resource = self._make_resource()
        payload = build_datacite_payload(resource, "10.20387", doi_suffix="s")
        self.assertIn("url", payload["data"]["attributes"])
        self.assertTrue(payload["data"]["attributes"]["url"].startswith("https://example.org/"))

    @patch("geonode.zalf.api.datacite.get_datacite_xml", return_value=None)
    def test_event_parameter_forwarded(self, mock_xml):
        resource = self._make_resource()
        payload = build_datacite_payload(resource, "10.20387", doi_suffix="s", event="register")
        self.assertEqual(payload["data"]["attributes"]["event"], "register")


# ---------------------------------------------------------------------------
# register_doi
# ---------------------------------------------------------------------------

@override_settings(**_SETTINGS, SITEURL="https://example.org/")
class TestRegisterDoi(TestCase):

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        cache.clear()
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group as DjangoGroup
        User = get_user_model()
        self.user = User.objects.create_user(username="reg_user", password="pw")
        grp, _ = DjangoGroup.objects.get_or_create(name="alpha-team")
        self.user.groups.add(grp)

    def _make_resource(self):
        from geonode.maps.models import Map
        return Map.objects.create(owner=self.user, title="Reg Test Map")

    def _mock_post(self, status_code=201, identifiers=None, doi=None):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = ""
        attrs = {}
        if identifiers is not None:
            attrs["identifiers"] = identifiers
        if doi is not None:
            attrs["doi"] = doi
        mock_resp.json.return_value = {"data": {"attributes": attrs}}
        return mock_resp

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account", return_value=["10.20387"])
    @patch("geonode.zalf.api.datacite.build_datacite_payload")
    @patch("geonode.zalf.api.datacite._requests.post")
    def test_returns_doi_from_identifiers_array(self, mock_post, mock_payload, mock_prefixes):
        mock_payload.return_value = {"data": {"type": "dois", "attributes": {"doi": "10.20387/x", "event": "publish", "url": "https://x"}}}
        mock_post.return_value = self._mock_post(
            status_code=201,
            identifiers=[{"identifierType": "DOI", "identifier": "https://handle.test.datacite.org/10.20387/x"}],
        )
        resource = self._make_resource()
        result = register_doi(resource, "10.20387", doi_suffix="x", user=self.user)
        self.assertEqual(result, "https://handle.test.datacite.org/10.20387/x")

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account", return_value=["10.20387"])
    @patch("geonode.zalf.api.datacite.build_datacite_payload")
    @patch("geonode.zalf.api.datacite._requests.post")
    def test_falls_back_to_doi_field_when_no_identifiers(self, mock_post, mock_payload, mock_prefixes):
        mock_payload.return_value = {"data": {"type": "dois", "attributes": {}}}
        mock_post.return_value = self._mock_post(status_code=201, identifiers=[], doi="10.20387/x")
        resource = self._make_resource()
        result = register_doi(resource, "10.20387", doi_suffix="x", user=self.user)
        # Should resolve to a fqdn via doi_to_fqdn
        self.assertTrue(result.startswith("https://"))
        self.assertIn("10.20387/x", result)

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account", return_value=["10.20387"])
    @patch("geonode.zalf.api.datacite.build_datacite_payload")
    @patch("geonode.zalf.api.datacite._requests.post")
    def test_doi_saved_to_resource(self, mock_post, mock_payload, mock_prefixes):
        mock_payload.return_value = {"data": {"type": "dois", "attributes": {}}}
        expected_doi = "https://handle.test.datacite.org/10.20387/saved"
        mock_post.return_value = self._mock_post(
            status_code=201,
            identifiers=[{"identifierType": "DOI", "identifier": expected_doi}],
        )
        resource = self._make_resource()
        register_doi(resource, "10.20387", doi_suffix="saved", user=self.user)
        resource.refresh_from_db()
        self.assertEqual(resource.doi, expected_doi)

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account", return_value=["10.20387"])
    @patch("geonode.zalf.api.datacite.build_datacite_payload")
    @patch("geonode.zalf.api.datacite._requests.post")
    def test_4xx_response_raises_validation_error(self, mock_post, mock_payload, mock_prefixes):
        mock_payload.return_value = {"data": {"type": "dois", "attributes": {}}}
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "Unprocessable"
        mock_resp.json.return_value = {
            "errors": [{"title": "Bad prefix", "detail": "Prefix not found"}]
        }
        mock_post.return_value = mock_resp
        resource = self._make_resource()
        with self.assertRaises(ValidationError) as ctx:
            register_doi(resource, "10.20387", doi_suffix="x", user=self.user)
        self.assertIn("Bad prefix", str(ctx.exception))

    @patch("geonode.zalf.api.datacite.fetch_prefixes_for_account", return_value=["10.20387"])
    @patch("geonode.zalf.api.datacite.build_datacite_payload")
    @patch("geonode.zalf.api.datacite._requests.post")
    def test_network_error_raises_validation_error(self, mock_post, mock_payload, mock_prefixes):
        import requests as _r
        mock_payload.return_value = {"data": {"type": "dois", "attributes": {}}}
        mock_post.side_effect = _r.exceptions.ConnectionError("connection refused")
        resource = self._make_resource()
        with self.assertRaises(ValidationError):
            register_doi(resource, "10.20387", doi_suffix="x", user=self.user)

    def test_invalid_prefix_raises_before_http_call(self):
        """validate_doi_prefix runs first — no HTTP call should be made."""
        with self.assertRaises(ValidationError):
            register_doi(MagicMock(), "BADPREFIX", user=self.user)

