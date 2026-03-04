#########################################################################
#
# Copyright (C) 2016 OSGeo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################
import logging

from django.urls import reverse
from django.contrib.auth import get_user_model

from geonode.base.models import Region
from geonode.layers.models import Dataset
from geonode.maps.models import Map, MapLayer
from geonode.base.models import LinkedResource
from geonode.tests.base import GeoNodeBaseTestSupport
from geonode.base.populate_test_data import all_public, create_models, remove_models

from geonode.maps.utils import (
    compare_metadata,
    get_all_syncable_fields,
    get_syncable_resources,
    sync_metadata,
    SYNC_SIMPLE_FIELDS,
    SYNC_M2M_FIELDS,
)

logger = logging.getLogger(__name__)


class MetadataSyncUtilsTest(GeoNodeBaseTestSupport):
    """Tests for geonode.maps.utils metadata sync functions."""

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_models(type=cls.get_type, integration=cls.get_integration)
        all_public()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        remove_models(cls.get_obj_ids, type=cls.get_type, integration=cls.get_integration)

    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.get(username="admin")
        self.map_obj = Map.objects.create(
            owner=self.admin,
            title="Test Map",
            abstract="Map abstract",
        )

    # ------------------------------------------------------------------ #
    # get_syncable_resources
    # ------------------------------------------------------------------ #
    def test_get_syncable_resources_empty(self):
        """A map with no linked resources or maplayers returns empty list."""
        resources = get_syncable_resources(self.map_obj)
        self.assertEqual(resources, [])

    def test_get_syncable_resources_with_maplayer(self):
        """MapLayer datasets are included in syncable resources."""
        dataset = Dataset.objects.all().first()
        if dataset is None:
            self.skipTest("No datasets available in test data")
        MapLayer.objects.create(
            map=self.map_obj,
            name=dataset.alternate or "test:layer",
            ows_url="http://localhost:8080/geoserver/wms",
            dataset=dataset,
        )
        resources = get_syncable_resources(self.map_obj)
        pks = [r.pk for r in resources]
        self.assertIn(dataset.pk, pks)

    def test_get_syncable_resources_with_linked_resource(self):
        """Explicit LinkedResource targets are included."""
        dataset = Dataset.objects.all().first()
        if dataset is None:
            self.skipTest("No datasets available in test data")
        LinkedResource.objects.create(
            source=self.map_obj,
            target=dataset,
            internal=False,
        )
        resources = get_syncable_resources(self.map_obj)
        pks = [r.pk for r in resources]
        self.assertIn(dataset.pk, pks)

    def test_get_syncable_resources_deduplicates(self):
        """A resource linked both via MapLayer and LinkedResource appears only once."""
        dataset = Dataset.objects.all().first()
        if dataset is None:
            self.skipTest("No datasets available in test data")
        MapLayer.objects.create(
            map=self.map_obj,
            name=dataset.alternate or "test:layer",
            ows_url="http://localhost:8080/geoserver/wms",
            dataset=dataset,
        )
        LinkedResource.objects.create(
            source=self.map_obj,
            target=dataset,
            internal=False,
        )
        resources = get_syncable_resources(self.map_obj)
        pks = [r.pk for r in resources]
        self.assertEqual(pks.count(dataset.pk), 1)

    # ------------------------------------------------------------------ #
    # compare_metadata
    # ------------------------------------------------------------------ #
    def test_compare_metadata_all_match(self):
        """Two resources with identical metadata should have all match=True."""
        other_map = Map.objects.create(
            owner=self.admin,
            title="Other Map",
            abstract="Map abstract",
        )
        # Ensure date fields match (auto-set on creation)
        other_map.date = self.map_obj.date
        other_map.save()
        diffs = compare_metadata(self.map_obj, other_map)
        self.assertTrue(len(diffs) > 0)
        for d in diffs:
            self.assertTrue(d["match"], f"Field {d['field']} should match but doesn't")

    def test_compare_metadata_detects_difference(self):
        """Differences in simple fields are detected."""
        other_map = Map.objects.create(
            owner=self.admin,
            title="Other Map",
            abstract="Different abstract",
        )
        diffs = compare_metadata(self.map_obj, other_map)
        abstract_diff = next(d for d in diffs if d["field"] == "abstract")
        self.assertFalse(abstract_diff["match"])
        self.assertEqual(abstract_diff["map_value"], "Map abstract")
        self.assertEqual(abstract_diff["resource_value"], "Different abstract")

    def test_compare_metadata_returns_expected_fields(self):
        """compare_metadata returns entries for all simple, M2M, and contact_role fields."""
        other_map = Map.objects.create(owner=self.admin, title="Other")
        diffs = compare_metadata(self.map_obj, other_map)
        field_names = [d["field"] for d in diffs]
        for f in SYNC_SIMPLE_FIELDS:
            self.assertIn(f, field_names, f"Simple field {f} missing from compare output")
        for f in SYNC_M2M_FIELDS:
            self.assertIn(f, field_names, f"M2M field {f} missing from compare output")
        self.assertIn("contact_roles", field_names)

    def test_compare_metadata_m2m_difference(self):
        """M2M field differences are detected (e.g., regions)."""
        other_map = Map.objects.create(owner=self.admin, title="Other")
        region = Region.objects.first()
        if region is None:
            self.skipTest("No regions available in test data")
        self.map_obj.regions.add(region)
        diffs = compare_metadata(self.map_obj, other_map)
        region_diff = next(d for d in diffs if d["field"] == "regions")
        self.assertFalse(region_diff["match"])

    # ------------------------------------------------------------------ #
    # sync_metadata
    # ------------------------------------------------------------------ #
    def test_sync_metadata_copies_simple_fields(self):
        """sync_metadata copies simple fields from map to resource."""
        target = Map.objects.create(
            owner=self.admin,
            title="Target",
            abstract="Old abstract",
        )
        self.map_obj.abstract = "New abstract from map"
        self.map_obj.purpose = "Test purpose"
        self.map_obj.save()

        sync_metadata(self.map_obj, target)
        target.refresh_from_db()

        self.assertEqual(target.abstract, "New abstract from map")
        self.assertEqual(target.purpose, "Test purpose")

    def test_sync_metadata_does_not_copy_title(self):
        """title and title_translated must NOT be synced."""
        target = Map.objects.create(
            owner=self.admin,
            title="Original Title",
        )
        self.map_obj.title = "Map Title"
        self.map_obj.save()

        sync_metadata(self.map_obj, target)
        target.refresh_from_db()

        self.assertEqual(target.title, "Original Title")

    def test_sync_metadata_copies_m2m_fields(self):
        """sync_metadata copies M2M fields like regions."""
        region = Region.objects.first()
        if region is None:
            self.skipTest("No regions available in test data")
        self.map_obj.regions.add(region)

        target = Map.objects.create(owner=self.admin, title="Target")
        sync_metadata(self.map_obj, target)

        self.assertIn(region, target.regions.all())

    def test_sync_metadata_makes_resources_match(self):
        """After sync, compare_metadata should show all fields matching."""
        target = Map.objects.create(
            owner=self.admin,
            title="Target",
            abstract="Different",
        )
        sync_metadata(self.map_obj, target)
        target.refresh_from_db()

        diffs = compare_metadata(self.map_obj, target)
        for d in diffs:
            self.assertTrue(d["match"], f"Field {d['field']} should match after sync")

    # ------------------------------------------------------------------ #
    # get_all_syncable_fields
    # ------------------------------------------------------------------ #
    def test_get_all_syncable_fields_returns_all(self):
        """get_all_syncable_fields returns entries for all simple, M2M, and contact_roles fields."""
        fields = get_all_syncable_fields()
        field_names = [f["field"] for f in fields]
        for fname in SYNC_SIMPLE_FIELDS:
            self.assertIn(fname, field_names, f"Simple field {fname} missing")
        for fname in SYNC_M2M_FIELDS:
            self.assertIn(fname, field_names, f"M2M field {fname} missing")
        self.assertIn("contact_roles", field_names)

    def test_get_all_syncable_fields_has_label_and_is_m2m(self):
        """Every entry from get_all_syncable_fields has 'field', 'label', and 'is_m2m' keys."""
        for f in get_all_syncable_fields():
            self.assertIn("field", f)
            self.assertIn("label", f)
            self.assertIn("is_m2m", f)
            self.assertIsInstance(f["label"], str)
            self.assertTrue(len(f["label"]) > 0)

    # ------------------------------------------------------------------ #
    # sync_metadata with field_names
    # ------------------------------------------------------------------ #
    def test_sync_metadata_with_field_names_subset(self):
        """sync_metadata only syncs the specified subset of fields."""
        target = Map.objects.create(
            owner=self.admin,
            title="Target",
            abstract="Old abstract",
            purpose="Old purpose",
        )
        self.map_obj.abstract = "New abstract"
        self.map_obj.purpose = "New purpose"
        self.map_obj.save()

        # Only sync abstract, not purpose
        sync_metadata(self.map_obj, target, field_names=["abstract"])
        target.refresh_from_db()

        self.assertEqual(target.abstract, "New abstract", "abstract should have been synced")
        self.assertEqual(target.purpose, "Old purpose", "purpose should NOT have been synced")

    def test_sync_metadata_field_names_empty_list_syncs_nothing(self):
        """sync_metadata with empty field_names syncs no fields."""
        target = Map.objects.create(
            owner=self.admin,
            title="Target",
            abstract="Original abstract",
        )
        self.map_obj.abstract = "Map abstract changed"
        self.map_obj.save()

        sync_metadata(self.map_obj, target, field_names=[])
        target.refresh_from_db()

        self.assertEqual(target.abstract, "Original abstract", "Nothing should change with empty field_names")


class MetadataSyncViewTest(GeoNodeBaseTestSupport):
    """Tests for the map_metadata_sync view."""

    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_models(type=cls.get_type, integration=cls.get_integration)
        all_public()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        remove_models(cls.get_obj_ids, type=cls.get_type, integration=cls.get_integration)

    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.get(username="admin")
        self.non_admin = get_user_model().objects.create(username="testuser", is_active=True)
        self.non_admin.set_password("testpass")
        self.non_admin.save()
        self.map_obj = Map.objects.create(owner=self.admin, title="Sync Test Map")

    def _url(self):
        return reverse("map_metadata_sync", kwargs={"mapid": self.map_obj.pk})

    # ------------------------------------------------------------------ #
    # Access control
    # ------------------------------------------------------------------ #
    def test_anonymous_redirected_to_login(self):
        """Unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_non_superuser_gets_forbidden(self):
        """Non-superusers get a 401/403 response."""
        self.client.login(username="testuser", password="testpass")
        response = self.client.get(self._url())
        self.assertIn(response.status_code, (401, 403))

    def test_superuser_can_access(self):
        """Superusers can access the sync page."""
        self.client.login(username="admin", password="admin")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------ #
    # GET behaviour
    # ------------------------------------------------------------------ #
    def test_get_context_contains_comparison_data(self):
        """GET renders comparison data in template context."""
        self.client.login(username="admin", password="admin")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("comparison_data", response.context)
        self.assertIn("total_diffs", response.context)
        self.assertIn("map", response.context)
        self.assertEqual(response.context["map"], self.map_obj)

    def test_get_with_linked_resource(self):
        """GET with linked resources shows non-empty comparison_data."""
        dataset = Dataset.objects.all().first()
        if dataset is None:
            self.skipTest("No datasets available in test data")
        MapLayer.objects.create(
            map=self.map_obj,
            name=dataset.alternate or "test:layer",
            ows_url="http://localhost:8080/geoserver/wms",
            dataset=dataset,
        )
        self.client.login(username="admin", password="admin")
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.context["comparison_data"]) > 0)

    # ------------------------------------------------------------------ #
    # POST behaviour
    # ------------------------------------------------------------------ #
    def test_post_syncs_selected_resources(self):
        """POST with selected resource_ids performs sync."""
        dataset = Dataset.objects.all().first()
        if dataset is None:
            self.skipTest("No datasets available in test data")
        self.map_obj.abstract = "Synced abstract"
        self.map_obj.save()
        MapLayer.objects.create(
            map=self.map_obj,
            name=dataset.alternate or "test:layer",
            ows_url="http://localhost:8080/geoserver/wms",
            dataset=dataset,
        )
        self.client.login(username="admin", password="admin")
        response = self.client.post(self._url(), data={"resource_ids": [str(dataset.pk)]})
        self.assertEqual(response.status_code, 302)  # redirects after POST

        dataset.refresh_from_db()
        self.assertEqual(dataset.abstract, "Synced abstract")

    def test_post_without_selection_shows_warning(self):
        """POST without selecting any resources redirects (with warning)."""
        self.client.login(username="admin", password="admin")
        response = self.client.post(self._url(), data={})
        self.assertEqual(response.status_code, 302)

    def test_post_does_not_sync_title(self):
        """POST sync must not overwrite the target resource's title."""
        dataset = Dataset.objects.all().first()
        if dataset is None:
            self.skipTest("No datasets available in test data")
        original_title = dataset.title
        self.map_obj.title = "Map Title Should Not Overwrite"
        self.map_obj.save()
        MapLayer.objects.create(
            map=self.map_obj,
            name=dataset.alternate or "test:layer",
            ows_url="http://localhost:8080/geoserver/wms",
            dataset=dataset,
        )
        self.client.login(username="admin", password="admin")
        self.client.post(self._url(), data={"resource_ids": [str(dataset.pk)]})

        dataset.refresh_from_db()
        self.assertEqual(dataset.title, original_title)

    def test_post_with_field_names_only_syncs_selected_fields(self):
        """POST with field_names should only sync the specified fields."""
        dataset = Dataset.objects.all().first()
        if dataset is None:
            self.skipTest("No datasets available in test data")

        original_purpose = dataset.purpose  # store original

        self.map_obj.abstract = "Synced abstract via field selection"
        self.map_obj.purpose = "Map purpose that should NOT be synced"
        self.map_obj.save()

        MapLayer.objects.create(
            map=self.map_obj,
            name=dataset.alternate or "test:layer",
            ows_url="http://localhost:8080/geoserver/wms",
            dataset=dataset,
        )
        self.client.login(username="admin", password="admin")
        response = self.client.post(
            self._url(),
            data={
                "resource_ids": [str(dataset.pk)],
                "field_names": ["abstract"],  # only sync abstract
            },
        )
        self.assertEqual(response.status_code, 302)

        dataset.refresh_from_db()
        self.assertEqual(dataset.abstract, "Synced abstract via field selection",
                         "abstract should have been synced")
        self.assertEqual(dataset.purpose, original_purpose,
                         "purpose must NOT be synced when not in field_names")
