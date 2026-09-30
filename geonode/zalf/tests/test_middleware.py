from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from geonode.zalf.middleware import KeycloakSilentSSOMiddleware, sso_cookie_domain


class SsoCookieDomainTests(SimpleTestCase):
    @override_settings(SITE_URL=None, SITEURL="https://repository-e.dataservice.zalf.de/")
    def test_uses_parent_domain_for_repository_subdomain(self):
        self.assertEqual(sso_cookie_domain(), ".dataservice.zalf.de")

    @override_settings(SITE_URL="http://localhost:8000", SITEURL=None)
    def test_uses_localhost_for_local_development(self):
        self.assertEqual(sso_cookie_domain(), "localhost")


@override_settings(
    SITE_URL=None,
    SITEURL="https://repository-e.dataservice.zalf.de/",
    SESSION_COOKIE_AGE=7200,
    SESSION_COOKIE_SECURE=True,
)
class KeycloakSilentSSOMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = KeycloakSilentSSOMiddleware(lambda request: HttpResponse())

    def test_authenticated_html_response_sets_shared_hint(self):
        request = self.factory.get("/", HTTP_ACCEPT="text/html")
        request.user = _User(is_authenticated=True)

        response = self.middleware(request)

        cookie = response.cookies["sso_hint"]
        self.assertEqual(cookie.value, "true")
        self.assertEqual(cookie["domain"], ".dataservice.zalf.de")
        self.assertEqual(cookie["max-age"], 7200)
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")
        self.assertTrue(cookie["secure"])
        self.assertFalse(cookie["httponly"])

    def test_anonymous_response_does_not_set_hint(self):
        request = self.factory.get("/", HTTP_ACCEPT="text/html")
        request.user = _User(is_authenticated=False)

        response = self.middleware(request)

        self.assertNotIn("sso_hint", response.cookies)

    def test_non_html_response_does_not_set_hint(self):
        request = self.factory.get("/api/v2/", HTTP_ACCEPT="application/json")
        request.user = _User(is_authenticated=True)

        response = self.middleware(request)

        self.assertNotIn("sso_hint", response.cookies)

    def test_logout_deletes_shared_hint(self):
        request = self.factory.post("/account/logout/")
        request.COOKIES["sso_hint"] = "true"
        request.user = _User(is_authenticated=False)

        response = self.middleware(request)

        cookie = response.cookies["sso_hint"]
        self.assertEqual(cookie.value, "")
        self.assertEqual(cookie["domain"], ".dataservice.zalf.de")
        self.assertEqual(cookie["max-age"], 0)
        self.assertEqual(cookie["path"], "/")


class _User:
    def __init__(self, *, is_authenticated):
        self.is_authenticated = is_authenticated
