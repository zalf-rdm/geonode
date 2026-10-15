"""
Unit tests for the landing page view counter
(POST /api/v2/resources/<pk>/view/) and the counters in the resource API.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from geonode.base.models import ResourceBase
from geonode.maps.models import Map

User = get_user_model()


# The counters must not depend on the environment:
# - auto publishing: a new resource is visible right away (no moderation workflow)
# - anonymous view granted by default
# - Keycloak SSO off: with SSO on, force_login sessions have no Keycloak binding
#   and are logged out by CentralSSOMiddleware
ENV = {
    "RESOURCE_PUBLISHING": False,
    "ADMIN_MODERATE_UPLOADS": False,
    "DEFAULT_ANONYMOUS_VIEW_PERMISSION": True,
    "KEYCLOAK_SSO_ENABLED": False,
}


def _create_map(owner, title="Counter Collection"):
    the_map = Map.objects.create(owner=owner, title=title)
    # as a real resource creation would: owner perms + default anonymous view
    the_map.set_default_permissions()
    return the_map


def _views(resource):
    return ResourceBase.objects.get(pk=resource.pk).popular_count


@override_settings(**ENV)
class TestCountResourceView(TestCase):
    # GeoServer OAuth app: logins get a real access token, otherwise
    # SessionControlMiddleware logs the force_login'ed users out again
    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.owner = User.objects.create_user(username="counter_owner", password="pw")
        self.visitor = User.objects.create_user(username="counter_visitor", password="pw")
        self.map = _create_map(self.owner)
        self.url = f"/api/v2/resources/{self.map.pk}/view/"

    def test_anonymous_view_is_counted_for_a_map(self):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(_views(self.map), 1)

    def test_same_session_counts_only_once(self):
        self.client.post(self.url)
        self.client.post(self.url)
        self.client.post(self.url)
        self.assertEqual(_views(self.map), 1)

    def test_different_sessions_count_separately(self):
        self.client.post(self.url)
        self.client.logout()
        self.client.cookies.clear()
        self.client.post(self.url)
        self.assertEqual(_views(self.map), 2)

    def test_logged_in_user_is_counted(self):
        self.client.force_login(self.visitor)
        self.client.post(self.url)
        self.assertEqual(_views(self.map), 1)

    def test_owner_is_not_counted(self):
        self.client.force_login(self.owner)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(_views(self.map), 0)

    def test_superuser_is_not_counted(self):
        admin = User.objects.create_user(username="counter_admin", password="pw", is_superuser=True)
        self.client.force_login(admin)
        self.client.post(self.url)
        self.assertEqual(_views(self.map), 0)

    def test_unknown_resource_returns_404(self):
        resp = self.client.post("/api/v2/resources/99999999/view/")
        self.assertEqual(resp.status_code, 404)

    def test_get_is_not_allowed(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(_views(self.map), 0)


@override_settings(**ENV)
class TestCountersInResourceApi(TestCase):
    def test_resource_api_returns_view_and_download_counters(self):
        owner = User.objects.create_user(username="api_owner", password="pw")
        the_map = _create_map(owner, title="Counter API")
        ResourceBase.objects.filter(pk=the_map.pk).update(popular_count=7, download_count=3)

        resp = self.client.get(f"/api/v2/resources/{the_map.pk}/")

        self.assertEqual(resp.status_code, 200)
        resource = resp.json()["resource"]
        self.assertEqual(resource["popular_count"], 7)
        self.assertEqual(resource["download_count"], 3)
