from urllib.parse import parse_qs, urlparse
from unittest.mock import patch, sentinel

from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model, login
from django.contrib.sessions.models import Session
from django.contrib.sessions.middleware import SessionMiddleware
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse
from django.http import HttpResponse

from geonode.zalf.views import global_logout_finalize, global_logout_start
from geonode.zalf.oidc import LogoutTokenAdapter, REAUTH_COOKIE, oidc_callback, oidc_login, require_next_login


@override_settings(
    UPLOAD_TOOL_GLOBAL_LOGOUT_URL="https://repository.example/upload/accounts/logout/global/",
    UPLOAD_TOOL_GLOBAL_LOGOUT_COMPLETE_URL="https://repository.example/upload/accounts/logout/global/complete/",
    ACCOUNT_LOGOUT_REDIRECT_URL="https://repository.example/",
    OIDC_POST_LOGOUT_REDIRECT_URL="https://repository.example/",
    SOCIALACCOUNT_PROVIDER_END_SESSION_URL=("https://identity.example/realms/ORCID/protocol/openid-connect/logout"),
    SOCIALACCOUNT_CLIENT_ID="repository-client",
    SOCIALACCOUNT_ONLY=True,
)
class GlobalLogoutTests(TestCase):
    def test_logout_marker_is_host_only_and_http_only(self):
        request = self.factory.get("/", secure=True)
        response = require_next_login(HttpResponse(), request)
        cookie = response.cookies[REAUTH_COOKIE]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")
        self.assertEqual(cookie["domain"], "")

    @patch("geonode.zalf.oidc.OAuth2LoginView.adapter_view")
    def test_next_login_forces_reauthentication_preserving_other_params(self, adapter_view):
        adapter_view.return_value = lambda request: HttpResponse()
        request = self.factory.get("/", {"auth_params": "kc_idp_hint=orcid&prompt=none"})
        request.COOKIES[REAUTH_COOKIE] = "1"
        oidc_login(request, "zalf")
        self.assertEqual(parse_qs(request.GET["auth_params"]), {"kc_idp_hint": ["orcid"], "prompt": ["login"]})

    @patch("geonode.zalf.oidc.OAuth2LoginView.adapter_view")
    def test_ordinary_login_preserves_cross_application_sso(self, adapter_view):
        adapter_view.return_value = lambda request: HttpResponse()
        request = self.factory.get("/")
        oidc_login(request, "zalf")
        self.assertNotIn("auth_params", request.GET)

    @patch("geonode.zalf.oidc.OAuth2CallbackView.adapter_view")
    def test_successful_login_clears_shared_reauthentication_marker(self, adapter_view):
        adapter_view.return_value = lambda request: HttpResponse()
        request = self.factory.get("/")
        request.user = self.user
        response = oidc_callback(request, "zalf")
        self.assertEqual(response.cookies[REAUTH_COOKIE]["max-age"], 0)

    @patch("geonode.zalf.oidc.OAuth2CallbackView.adapter_view")
    def test_failed_login_keeps_reauthentication_marker(self, adapter_view):
        adapter_view.return_value = lambda request: HttpResponse()
        request = self.factory.get("/")
        request.user = AnonymousUser()
        response = oidc_callback(request, "zalf")
        self.assertNotIn(REAUTH_COOKIE, response.cookies)

    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(username="logout-test", email="logout@example.com")

    def _request(self, method, path):
        request = getattr(self.factory, method)(path)
        SessionMiddleware(lambda value: None).process_request(request)
        request.user = AnonymousUser()
        request._dont_enforce_csrf_checks = True
        return request

    def test_logout_page_exposes_one_automatic_global_action(self):
        html = render_to_string(
            "account/logout.html",
            {"global_logout_action_url": reverse("global_logout_start")},
        )

        self.assertIn('id="global-logout-form"', html)
        self.assertIn(reverse("global_logout_start"), html)
        self.assertNotIn("logout_orcid", html)
        self.assertNotIn("application only", html)

    def test_start_keeps_geonode_session_and_redirects_to_upload_tool(self):
        request = self._request("post", reverse("global_logout_start"))
        request.session["session-marker"] = "preserved"

        response = global_logout_start(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://repository.example/upload/accounts/logout/global/",
        )
        self.assertEqual(request.session["session-marker"], "preserved")

    def test_finalize_page_automatically_posts_to_itself(self):
        request = self._request("get", reverse("global_logout_finalize"))

        response = global_logout_finalize(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="global-logout-finalize-form"', response.content)
        self.assertIn(reverse("global_logout_finalize").encode(), response.content)

    def test_finalize_ends_geonode_and_identity_sessions_then_returns_home(self):
        request = self._request("post", reverse("global_logout_finalize"))
        request.session["session-marker"] = "authenticated"
        request.session["oidc_id_token"] = "signed-id-token"

        response = global_logout_finalize(request)

        location = urlparse(response["Location"])
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}",
            "https://identity.example/realms/ORCID/protocol/openid-connect/logout",
        )
        self.assertEqual(
            parse_qs(location.query),
            {
                "id_token_hint": ["signed-id-token"],
                "post_logout_redirect_uri": ["https://repository.example/upload/accounts/logout/global/complete/"],
            },
        )
        self.assertNotIn("session-marker", request.session)
        self.assertEqual(response.cookies[REAUTH_COOKIE].value, "1")

    def test_legacy_social_session_uses_client_id_fallback(self):
        request = self._request("post", reverse("global_logout_finalize"))
        request.user = self.user

        response = global_logout_finalize(request)

        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query["client_id"], ["repository-client"])
        self.assertEqual(
            query["post_logout_redirect_uri"],
            ["https://repository.example/upload/accounts/logout/global/complete/"],
        )

    @override_settings(SOCIALACCOUNT_ONLY=False)
    def test_local_login_falls_back_to_repository_home(self):
        request = self._request("post", reverse("global_logout_finalize"))
        request.session["session-marker"] = "authenticated"

        response = global_logout_finalize(request)

        self.assertEqual(response["Location"], "https://repository.example/upload/accounts/logout/global/complete/")
        self.assertNotIn("session-marker", request.session)

    def test_authenticated_session_is_deleted_server_side(self):
        request = self._request("post", reverse("global_logout_finalize"))
        login(request, self.user, backend="django.contrib.auth.backends.ModelBackend")
        request.session.save()
        previous_key = request.session.session_key
        self.assertTrue(Session.objects.filter(session_key=previous_key).exists())

        global_logout_finalize(request)

        self.assertFalse(request.user.is_authenticated)
        self.assertFalse(Session.objects.filter(session_key=previous_key).exists())

    def test_canonical_logout_and_oidc_routes_use_custom_views(self):
        self.assertEqual(resolve("/account/logout/").func, global_logout_start)
        self.assertEqual(resolve("/account/oidc/zalf/login/").func, oidc_login)
        self.assertEqual(resolve("/account/oidc/zalf/login/callback/").func, oidc_callback)

    def test_cross_site_get_does_not_automatically_post(self):
        request = self._request("get", reverse("global_logout_start"))
        request.META["HTTP_SEC_FETCH_SITE"] = "cross-site"
        response = global_logout_start(request)
        self.assertNotIn(b"document.getElementById('global-logout-form').submit();", response.content)

    def test_same_site_get_automatically_posts(self):
        request = self._request("get", reverse("global_logout_start"))
        request.META["HTTP_SEC_FETCH_SITE"] = "same-site"
        self.assertIn(b"document.getElementById('global-logout-form').submit();", global_logout_start(request).content)

    def test_post_without_csrf_does_not_clear_session(self):
        request = self._request("post", reverse("global_logout_finalize"))
        request._dont_enforce_csrf_checks = False
        request.session["session-marker"] = "preserved"
        self.assertEqual(global_logout_finalize(request).status_code, 403)
        self.assertEqual(request.session["session-marker"], "preserved")

    @patch("allauth.socialaccount.providers.openid_connect.views.OpenIDConnectOAuth2Adapter.complete_login")
    def test_real_oidc_callback_retains_user_id_token(self, complete_login):
        complete_login.return_value = sentinel.sociallogin
        request = self._request("get", "/account/oidc/zalf/login/callback/")
        adapter = LogoutTokenAdapter(request, "zalf")
        result = adapter.complete_login(request, None, None, response={"id_token": "signed-user-token"})
        self.assertIs(result, sentinel.sociallogin)
        self.assertEqual(request.session["oidc_id_token"], "signed-user-token")
        self.assertTrue(request.session["oidc_login"])

    @patch("allauth.socialaccount.providers.openid_connect.views.OpenIDConnectOAuth2Adapter.complete_login")
    def test_failed_oidc_callback_does_not_store_token(self, complete_login):
        complete_login.side_effect = ValueError("invalid token")
        request = self._request("get", "/account/oidc/zalf/login/callback/")
        adapter = LogoutTokenAdapter(request, "zalf")
        with self.assertRaises(ValueError):
            adapter.complete_login(request, None, None, response={"id_token": "invalid-token"})
        self.assertNotIn("oidc_id_token", request.session)
