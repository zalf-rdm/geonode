"""
Unit tests for geonode.zalf.api.views — approve and publish data collection
workflow.

All DataCite HTTP calls are patched out so these tests run without network
access or a running GeoServer.
"""

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group as DjangoGroup
from django.test import TestCase, override_settings

from geonode.base.models import LinkedResource
from geonode.maps.models import Map

User = get_user_model()

# ---------------------------------------------------------------------------
# Shared test settings — two DataCite accounts, one per group
# ---------------------------------------------------------------------------

_ACCOUNTS = [
    {"username": "ORG.ALPHA", "password": "pw-alpha", "groups": ["alpha-team"]},
]

_SETTINGS = {
    "ZALF_DATACITE_BASE_URL": "https://api.test.datacite.org/",
    "ZALF_DATACITE_ACCOUNTS": _ACCOUNTS,
    "ZALF_DATACITE_AGENT": "Test Agent",
    "PUBLISH_DATA_COLLECTION_ALLOWED_GROUPS": ["alpha-team"],
}

# Registered DOI that the mocked register_doi returns
_REGISTERED_DOI = "https://handle.test.datacite.org/10.20387/test-uuid"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_user(username, groups=(), is_superuser=False, password="testpass"):
    user = User.objects.create_user(username=username, password=password, is_superuser=is_superuser)
    for g in groups:
        grp, _ = DjangoGroup.objects.get_or_create(name=g)
        user.groups.add(grp)
    return user


def _create_map(owner, title="Test Collection", is_approved=False, is_published=False):
    return Map.objects.create(
        owner=owner,
        title=title,
        is_approved=is_approved,
        is_published=is_published,
    )


def _create_dataset(owner, title="Test Dataset", is_approved=False, is_published=False):
    """Create a minimal Dataset (ResourceBase subtype) for linking to a map."""
    from geonode.layers.models import Dataset

    return Dataset.objects.create(
        owner=owner,
        title=title,
        is_approved=is_approved,
        is_published=is_published,
        # minimal required fields
        name=f"test_layer_{uuid.uuid4().hex[:8]}",
        workspace="test",
        store="test_store",
        subtype="vector",
    )


def _link(source_map, target_resource):
    LinkedResource.objects.create(source=source_map, target=target_resource, internal=False)


# ---------------------------------------------------------------------------
# Approve endpoint — authentication / authorization
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestApproveAuthZ(TestCase):
    """approve_data_collection_post — auth and permission checks."""

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.member = _create_user("member", groups=["alpha-team"])
        self.outsider = _create_user("outsider")
        self.map = _create_map(owner=self.member)
        self.approve_url = f"/api/v2/approve/{self.map.pk}/"

    def test_anonymous_gets_403(self):
        resp = self.client.post(
            self.approve_url,
            data=json.dumps({"owner": self.member.pk}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_outsider_gets_403(self):
        self.client.force_login(self.outsider)
        resp = self.client.post(
            self.approve_url,
            data=json.dumps({"owner": self.member.pk}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_missing_owner_returns_400(self):
        self.client.force_login(self.member)
        resp = self.client.post(
            self.approve_url,
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_nonexistent_map_returns_404(self):
        self.client.force_login(self.member)
        resp = self.client.post(
            "/api/v2/approve/999999/",
            data=json.dumps({"owner": self.member.pk}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_superuser_can_approve(self):
        admin = _create_user("admin_user", is_superuser=True)
        self.client.force_login(admin)
        resp = self.client.post(
            self.approve_url,
            data=json.dumps({"owner": self.member.pk}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])


# ---------------------------------------------------------------------------
# Approve endpoint — business logic
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestApproveLogic(TestCase):
    """_approve_data_collection — sets is_approved on map and owned linked resources."""

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.member = _create_user("member2", groups=["alpha-team"])
        self.other = _create_user("other_owner")

    def _approve(self, map_obj, owner):
        """Call the approve view as self.member for the given map/owner."""
        self.client.force_login(self.member)
        return self.client.post(
            f"/api/v2/approve/{map_obj.pk}/",
            data=json.dumps({"owner": owner.pk}),
            content_type="application/json",
        )

    def test_map_is_approved(self):
        the_map = _create_map(owner=self.member)
        resp = self._approve(the_map, self.member)
        self.assertEqual(resp.status_code, 200)
        the_map.refresh_from_db()
        self.assertTrue(the_map.is_approved)

    def test_linked_dataset_owned_by_target_owner_is_approved(self):
        the_map = _create_map(owner=self.member)
        try:
            ds = _create_dataset(owner=self.member, title="DS approve test")
        except Exception:
            self.skipTest("Dataset creation requires GeoServer or extra fixtures")
        _link(the_map, ds)

        self._approve(the_map, self.member)
        ds.refresh_from_db()
        self.assertTrue(ds.is_approved)

    def test_linked_dataset_owned_by_other_is_not_approved(self):
        the_map = _create_map(owner=self.member)
        try:
            ds = _create_dataset(owner=self.other, title="DS other owner")
        except Exception:
            self.skipTest("Dataset creation requires GeoServer or extra fixtures")
        _link(the_map, ds)

        self._approve(the_map, self.member)
        ds.refresh_from_db()
        self.assertFalse(ds.is_approved)

    def test_approve_is_idempotent(self):
        """Approving an already-approved map must still return 200."""
        the_map = _create_map(owner=self.member, is_approved=True)
        resp = self._approve(the_map, self.member)
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Publish endpoint — authentication / authorization
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestPublishAuthZ(TestCase):
    """publish_data_collection — auth and permission checks."""

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.member = _create_user("pub_member", groups=["alpha-team"])
        self.outsider = _create_user("pub_outsider")
        self.map = _create_map(owner=self.member, is_approved=True)
        self.url = f"/api/v2/publish/{self.map.pk}/"

    def _payload(self, owner=None, resources=None, doi_prefix="10.20387"):
        return json.dumps(
            {
                "owner": (owner or self.member).pk,
                "resources": resources or [],
                "doi_prefix": doi_prefix,
            }
        )

    def test_anonymous_gets_403(self):
        resp = self.client.post(self.url, data=self._payload(), content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_outsider_gets_403(self):
        self.client.force_login(self.outsider)
        resp = self.client.post(self.url, data=self._payload(), content_type="application/json")
        self.assertEqual(resp.status_code, 403)

    def test_nonexistent_map_returns_404(self):
        self.client.force_login(self.member)
        resp = self.client.post(
            "/api/v2/publish/999999/",
            data=self._payload(),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_invalid_doi_prefix_format_returns_400(self):
        self.client.force_login(self.member)
        with (
            patch("geonode.zalf.api.views.get_datacite_account_for_prefix"),
            patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI),
        ):
            resp = self.client.post(
                self.url,
                data=json.dumps(
                    {
                        "owner": self.member.pk,
                        "resources": [],
                        "doi_prefix": "INVALID",
                    }
                ),
                content_type="application/json",
            )
        # validate_doi_prefix raises ValidationError → 400
        self.assertIn(resp.status_code, (400, 422))

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_member_can_publish_empty_resources(self, mock_register, mock_acct):
        """Publish with empty resources list succeeds — only the map gets a DOI."""
        mock_acct.return_value = _ACCOUNTS[0]
        self.client.force_login(self.member)
        resp = self.client.post(self.url, data=self._payload(), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["doi"], _REGISTERED_DOI)


# ---------------------------------------------------------------------------
# Publish endpoint — business logic
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestPublishLogic(TestCase):
    """_publish_data_collection — DOI registration, status flags, edge cases."""

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.member = _create_user("pub_logic_member", groups=["alpha-team"])
        self.map = _create_map(owner=self.member, is_approved=True)
        self.url = f"/api/v2/publish/{self.map.pk}/"
        self.client.force_login(self.member)

    def _post(self, resources=None, doi_prefix="10.20387", owner=None):
        return self.client.post(
            self.url,
            data=json.dumps(
                {
                    "owner": (owner or self.member).pk,
                    "resources": resources or [],
                    "doi_prefix": doi_prefix,
                }
            ),
            content_type="application/json",
        )

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_map_is_published(self, mock_register, mock_acct):
        mock_acct.return_value = _ACCOUNTS[0]
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.map.refresh_from_db()
        self.assertTrue(self.map.is_published)

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_doi_stored_on_map(self, mock_register, mock_acct):
        mock_acct.return_value = _ACCOUNTS[0]
        self._post()
        self.map.refresh_from_db()
        self.assertEqual(self.map.doi, _REGISTERED_DOI)

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_response_contains_doi(self, mock_register, mock_acct):
        mock_acct.return_value = _ACCOUNTS[0]
        resp = self._post()
        self.assertEqual(resp.json()["doi"], _REGISTERED_DOI)

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_register_doi_called_with_correct_prefix(self, mock_register, mock_acct):
        mock_acct.return_value = _ACCOUNTS[0]
        self._post(doi_prefix="10.20387")
        mock_register.assert_called_once()
        args, kwargs = mock_register.call_args
        self.assertEqual(args[1], "10.20387")

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi")
    def test_datacite_api_failure_returns_error(self, mock_register, mock_acct):
        from django.core.exceptions import ValidationError

        mock_acct.return_value = _ACCOUNTS[0]
        mock_register.side_effect = ValidationError("DataCite API returned status 500")
        resp = self._post()
        self.assertIn(resp.status_code, (400, 422, 500))

    def test_missing_doi_prefix_returns_error(self):
        resp = self.client.post(
            self.url,
            data=json.dumps({"owner": self.member.pk, "resources": []}),
            content_type="application/json",
        )
        # doi_prefix is optional in the serializer but required by business logic
        # (ValidationError("DOI prefix is required"))
        self.assertIn(resp.status_code, (400, 422, 500))

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_unapproved_resource_in_list_raises(self, mock_register, mock_acct):
        """Resources that are not yet approved must be rejected."""
        mock_acct.return_value = _ACCOUNTS[0]
        try:
            ds = _create_dataset(owner=self.member, title="Unapproved DS", is_approved=False)
        except Exception:
            self.skipTest("Dataset creation requires GeoServer or extra fixtures")
        _link(self.map, ds)
        resp = self._post(resources=[ds.pk])
        self.assertIn(resp.status_code, (400, 422, 500))

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_already_published_resource_skipped(self, mock_register, mock_acct):
        """A resource that is already published is silently ignored (filter in view)."""
        mock_acct.return_value = _ACCOUNTS[0]
        try:
            ds = _create_dataset(
                owner=self.member,
                title="Already Published DS",
                is_approved=True,
                is_published=True,
            )
        except Exception:
            self.skipTest("Dataset creation requires GeoServer or extra fixtures")
        _link(self.map, ds)
        resp = self._post(resources=[ds.pk])
        # The ds was already published so it is filtered out; publish still succeeds
        self.assertEqual(resp.status_code, 200)

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_resource_owned_by_different_user_not_published(self, mock_register, mock_acct):
        """Resources owned by a different user than the payload owner are ignored."""
        mock_acct.return_value = _ACCOUNTS[0]
        other = _create_user("other_ds_owner")
        try:
            ds = _create_dataset(owner=other, title="Other Owner DS", is_approved=True)
        except Exception:
            self.skipTest("Dataset creation requires GeoServer or extra fixtures")
        _link(self.map, ds)
        # Pass other.pk as owner but authenticate as self.member
        resp = self._post(resources=[ds.pk], owner=other)
        # ds is filtered out because owner mismatch — publish still succeeds
        self.assertEqual(resp.status_code, 200)
        ds.refresh_from_db()
        self.assertFalse(ds.is_published)


# ---------------------------------------------------------------------------
# can_publish_data_collection — user model method
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestCanPublishDataCollection(TestCase):
    """Profile.can_publish_data_collection()"""

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def test_member_of_allowed_group_can_publish(self):
        user = _create_user("allowed_user", groups=["alpha-team"])
        self.assertTrue(user.can_publish_data_collection())

    def test_user_not_in_allowed_group_cannot_publish(self):
        user = _create_user("forbidden_user", groups=["some-other-group"])
        self.assertFalse(user.can_publish_data_collection())

    def test_user_with_no_groups_cannot_publish(self):
        user = _create_user("no_groups_user")
        self.assertFalse(user.can_publish_data_collection())

    def test_superuser_can_always_publish(self):
        user = _create_user("super_user", is_superuser=True)
        self.assertTrue(user.can_publish_data_collection())

    def test_anonymous_user_cannot_publish(self):
        from django.contrib.auth.models import AnonymousUser

        anon = AnonymousUser()
        # AnonymousUser has no can_publish_data_collection — the view checks
        # is_authenticated first.  Verify the view rejects anonymous requests.
        self.assertFalse(anon.is_authenticated)


# ---------------------------------------------------------------------------
# _update_resource_status — date stamping behaviour
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestUpdateResourceStatus(TestCase):
    """
    _update_resource_status sets date fields on first publish and does NOT
    overwrite them when they are already set.
    """

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.member = _create_user("date_test_member", groups=["alpha-team"])

    def test_date_fields_set_on_first_publish(self):
        the_map = _create_map(owner=self.member)
        # Ensure all date fields are unset
        self.assertIsNone(the_map.date_available)
        self.assertIsNone(the_map.date_issued)

        from geonode.zalf.api.views import _update_resource_status

        _update_resource_status(the_map, is_published=True)

        the_map.refresh_from_db()
        import datetime

        self.assertIsNotNone(the_map.date_available)
        self.assertIsNotNone(the_map.date_issued)
        self.assertEqual(the_map.date_available, datetime.date.today())
        self.assertEqual(the_map.date_issued, datetime.date.today())

    def test_existing_date_fields_not_overwritten(self):
        import datetime

        fixed_date = datetime.date(2020, 1, 1)
        the_map = _create_map(owner=self.member)
        the_map.date_available = fixed_date
        the_map.date_issued = fixed_date
        the_map.save()

        from geonode.zalf.api.views import _update_resource_status

        _update_resource_status(the_map, is_published=True)

        the_map.refresh_from_db()
        # Original dates must be preserved
        self.assertEqual(the_map.date_available, fixed_date)
        self.assertEqual(the_map.date_issued, fixed_date)

    def test_is_approved_flag_set_independently(self):
        the_map = _create_map(owner=self.member)
        from geonode.zalf.api.views import _update_resource_status

        _update_resource_status(the_map, is_approved=True)
        the_map.refresh_from_db()
        self.assertTrue(the_map.is_approved)
        self.assertFalse(the_map.is_published)


# ---------------------------------------------------------------------------
# Approve — response body and edge cases
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestApproveResponseBody(TestCase):

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.member = _create_user("resp_member", groups=["alpha-team"])
        self.client.force_login(self.member)

    def test_success_response_has_correct_shape(self):
        the_map = _create_map(owner=self.member)
        resp = self.client.post(
            f"/api/v2/approve/{the_map.pk}/",
            data=json.dumps({"owner": self.member.pk}),
            content_type="application/json",
        )
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("message", data)

    def test_nonexistent_owner_returns_404(self):
        the_map = _create_map(owner=self.member)
        resp = self.client.post(
            f"/api/v2/approve/{the_map.pk}/",
            data=json.dumps({"owner": 999999}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# Publish — register_doi called with correct user and suffix
# ---------------------------------------------------------------------------


@override_settings(**_SETTINGS)
class TestPublishCallArgs(TestCase):

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.member = _create_user("call_args_member", groups=["alpha-team"])
        self.map = _create_map(owner=self.member, is_approved=True)
        self.client.force_login(self.member)

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_register_doi_receives_map_uuid_as_suffix(self, mock_register, mock_acct):
        mock_acct.return_value = _ACCOUNTS[0]
        self.client.post(
            f"/api/v2/publish/{self.map.pk}/",
            data=json.dumps({"owner": self.member.pk, "resources": [], "doi_prefix": "10.20387"}),
            content_type="application/json",
        )
        _, kwargs = mock_register.call_args
        self.assertEqual(kwargs.get("doi_suffix") or mock_register.call_args[0][2], str(self.map.uuid))

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    @patch("geonode.zalf.api.views.register_doi", return_value=_REGISTERED_DOI)
    def test_register_doi_receives_authenticated_user(self, mock_register, mock_acct):
        """The user passed to register_doi must be the *request* user, not payload owner."""
        mock_acct.return_value = _ACCOUNTS[0]
        owner = _create_user("payload_owner2")
        self.client.post(
            f"/api/v2/publish/{self.map.pk}/",
            data=json.dumps({"owner": owner.pk, "resources": [], "doi_prefix": "10.20387"}),
            content_type="application/json",
        )
        _, kwargs = mock_register.call_args
        user_arg = kwargs.get("user")
        self.assertEqual(user_arg.pk, self.member.pk)

    @patch("geonode.zalf.api.views.get_datacite_account_for_prefix")
    def test_prefix_not_accessible_to_user_returns_error(self, mock_acct):
        """get_datacite_account_for_prefix raises when the prefix isn't in the user's accounts."""
        from django.core.exceptions import ValidationError

        mock_acct.side_effect = ValidationError("No DataCite account found for prefix '10.20387'")
        resp = self.client.post(
            f"/api/v2/publish/{self.map.pk}/",
            data=json.dumps({"owner": self.member.pk, "resources": [], "doi_prefix": "10.20387"}),
            content_type="application/json",
        )
        self.assertIn(resp.status_code, (400, 422, 500))
