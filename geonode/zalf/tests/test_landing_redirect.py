"""
Tests for /landing/<uuid>/, the stable landing page link used as DOI target (#823).
"""

import uuid
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from geonode.maps.models import Map
from geonode.zalf.views import landing_page_url

User = get_user_model()

# Independent of the environment: resources visible to anonymous users, no Keycloak SSO.
ENV = {
    "RESOURCE_PUBLISHING": False,
    "ADMIN_MODERATE_UPLOADS": False,
    "DEFAULT_ANONYMOUS_VIEW_PERMISSION": True,
    "KEYCLOAK_SSO_ENABLED": False,
}


def _resource(resource_type, subtype=None, pk=7):
    return SimpleNamespace(
        resource_type=resource_type,
        subtype=subtype,
        pk=pk,
        get_absolute_url=lambda: f"/catalogue/#/{resource_type}/{pk}",
    )


class TestLandingPageUrl(SimpleTestCase):
    def test_map_goes_to_map_landing_page(self):
        self.assertEqual(landing_page_url(_resource("map")), "/catalogue/#/landing/map/7")

    def test_table_collection_keeps_its_route(self):
        self.assertEqual(
            landing_page_url(_resource("map", "tabular-collection")), "/catalogue/#/landing/tabular-collection/7"
        )

    def test_datasets_including_tables_go_to_dataset_landing_page(self):
        self.assertEqual(landing_page_url(_resource("dataset", "vector")), "/catalogue/#/landing/dataset/7")
        self.assertEqual(landing_page_url(_resource("dataset", "tabular")), "/catalogue/#/landing/dataset/7")

    def test_document(self):
        self.assertEqual(landing_page_url(_resource("document")), "/catalogue/#/landing/document/7")

    def test_other_types_keep_their_own_page(self):
        self.assertEqual(landing_page_url(_resource("geostory")), "/catalogue/#/geostory/7")


@override_settings(**ENV)
class TestResolveLandingUuid(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username="landing_owner", password="pw")
        self.map = Map.objects.create(owner=owner, title="Landing Collection")
        self.map.set_default_permissions()

    def test_uuid_redirects_to_landing_page(self):
        resp = self.client.get(f"/landing/{self.map.uuid}/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f"/catalogue/#/landing/map/{self.map.pk}")

    def test_trailing_slash_is_optional(self):
        resp = self.client.get(f"/landing/{self.map.uuid}")
        self.assertEqual(resp.status_code, 302)

    def test_unknown_uuid_returns_404(self):
        resp = self.client.get(f"/landing/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)
