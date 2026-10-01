import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model, login
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, RequestFactory, TestCase, override_settings

from repository_sso.checks import check_sso
from repository_sso.models import LogoutEvent, SessionBinding
from repository_sso.protocol import LOGOUT_EVENT, validate_logout_token, revoke_sessions
from repository_sso.oidc import SessionOIDCAdapter

ISSUER = "https://identity.example/realms/repository"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class CentralSSOTests(TestCase):
    def setUp(self):
        self.key_patch = patch(
            "repository_sso.protocol.signing_keys",
            return_value=SimpleNamespace(
                get_signing_key_from_jwt=lambda token: SimpleNamespace(
                    key=KEY.public_key()
                )
            ),
        )
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.user = get_user_model().objects.create_user(
            username="existing", password="local-password"
        )
        self.factory = RequestFactory()

    def token(self, **changes):
        claims = {
            "iss": ISSUER,
            "aud": "repository",
            "iat": int(time.time()),
            "jti": "event-one",
            "sid": "sso-session",
            "sub": "keycloak-user",
            "events": {LOGOUT_EVENT: {}},
        }
        claims.update(changes)
        return jwt.encode(claims, KEY, algorithm="RS256")

    def binding(
        self, client=None, sid="sso-session", subject="keycloak-user", issued_at=None
    ):
        client = client or self.client
        client.force_login(self.user)
        session = client.session
        session["repository_sso_id_token"] = "real-user-id-token"
        session["repository_sso_check_after"] = time.time() + 60
        session.save()
        return SessionBinding.objects.create(
            session_key=session.session_key,
            issuer=ISSUER,
            subject=subject,
            sid=sid,
            issued_at=issued_at or int(time.time()) - 20,
            check_after=int(time.time()) + 60,
        )

    def test_signed_backchannel_revokes_matching_session_and_cookie_replay(self):
        binding = self.binding()
        old_cookie = self.client.cookies["repository_session"].value
        response = Client().post(
            "/sso/backchannel-logout/", {"logout_token": self.token()}
        )
        self.assertEqual(response.status_code, 200)
        binding.refresh_from_db()
        self.assertTrue(binding.revoked)
        self.client.cookies["repository_session"] = old_cookie
        self.assertEqual(self.client.get("/protected/").status_code, 302)
        self.assertFalse(
            SessionStore(session_key=binding.session_key).exists(binding.session_key)
        )

    def test_other_sso_sessions_and_subjects_survive(self):
        self.binding()
        another_client = Client()
        other = self.binding(another_client, sid="other-session")
        self.client.post("/sso/backchannel-logout/", {"logout_token": self.token()})
        other.refresh_from_db()
        self.assertFalse(other.revoked)
        self.assertEqual(another_client.get("/protected/").status_code, 200)

    def test_subject_logout_revokes_all_subject_sessions(self):
        self.binding()
        other = self.binding(Client(), sid="other-session")
        unrelated = self.binding(Client(), subject="another-user")
        claims = jwt.decode(self.token(), options={"verify_signature": False})
        claims.pop("sid")
        revoke_sessions(
            validate_logout_token(jwt.encode(claims, KEY, algorithm="RS256"))
        )
        other.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertTrue(other.revoked)
        self.assertFalse(unrelated.revoked)

    def test_newer_authentication_is_not_revoked_by_older_event(self):
        new = self.binding(sid="new-session", issued_at=int(time.time()) + 1)
        revoke_sessions(validate_logout_token(self.token()))
        new.refresh_from_db()
        self.assertFalse(new.revoked)

    def test_revocation_blocks_late_login_callback(self):
        revoke_sessions(validate_logout_token(self.token()))
        request = self.factory.get("/")
        request.session = SessionStore()
        claims = {
            "iss": ISSUER,
            "sub": "keycloak-user",
            "sid": "sso-session",
            "iat": int(time.time()) - 20,
        }
        request.repository_sso_identity = (claims, "id-token")
        login(request, self.user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertTrue(
            SessionBinding.objects.get(session_key=request.session.session_key).revoked
        )

    def test_jwt_replay_is_rejected(self):
        token = self.token()
        self.assertEqual(
            self.client.post(
                "/sso/backchannel-logout/", {"logout_token": token}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/sso/backchannel-logout/", {"logout_token": token}
            ).status_code,
            400,
        )
        self.assertEqual(LogoutEvent.objects.count(), 1)

    def test_invalid_claims_never_revoke_sessions(self):
        binding = self.binding()
        changes = [
            {"iss": "https://attacker.example"},
            {"aud": "other-client"},
            {"iat": int(time.time()) - 400},
            {"iat": int(time.time()) + 100},
            {"events": {}},
            {"events": {LOGOUT_EVENT: "invalid"}},
            {"nonce": "forbidden"},
            {"sid": None, "sub": None},
            {"jti": ""},
            {"sid": 25},
            {"sub": ""},
            {"iat": True},
        ]
        for claims in changes:
            with self.subTest(claims=claims):
                self.assertEqual(
                    self.client.post(
                        "/sso/backchannel-logout/",
                        {"logout_token": self.token(**claims)},
                    ).status_code,
                    400,
                )
        binding.refresh_from_db()
        self.assertFalse(binding.revoked)

    def test_forged_unsigned_and_malformed_tokens_rejected(self):
        claims = jwt.decode(self.token(), options={"verify_signature": False})
        for token in (
            jwt.encode(claims, OTHER_KEY, algorithm="RS256"),
            jwt.encode(claims, "", algorithm="none"),
            "malformed",
            "",
            "x" * 17000,
        ):
            self.assertEqual(
                self.client.post(
                    "/sso/backchannel-logout/", {"logout_token": token}
                ).status_code,
                400,
            )

    def test_backchannel_is_post_only_and_csrf_exempt(self):
        self.assertEqual(self.client.get("/sso/backchannel-logout/").status_code, 405)
        self.assertEqual(
            Client(enforce_csrf_checks=True)
            .post("/sso/backchannel-logout/", {"logout_token": self.token()})
            .status_code,
            200,
        )

    def test_key_server_outage_returns_retryable_response(self):
        with patch(
            "repository_sso.protocol.signing_keys",
            side_effect=jwt.PyJWKClientConnectionError("offline"),
        ):
            self.assertEqual(
                self.client.post(
                    "/sso/backchannel-logout/", {"logout_token": self.token()}
                ).status_code,
                503,
            )

    def test_all_browser_login_entries_use_keycloak(self):
        for path in (
            "/account/login/",
            "/admin/login/",
            "/dev-login/",
            "/account/ajax_login",
        ):
            with self.subTest(path=path):
                response = self.client.get(path + "?next=/protected/")
                self.assertEqual(response.status_code, 302)
                self.assertTrue(
                    response.url.startswith("/account/oidc/keycloak/login/")
                )
                self.assertEqual(
                    parse_qs(urlparse(response.url).query)["next"], ["/protected/"]
                )

    def test_local_password_login_cannot_authenticate(self):
        self.client.post(
            "/account/login/", {"login": "existing", "password": "local-password"}
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_and_password_reset_are_disabled(self):
        for path in (
            "/account/signup/",
            "/account/password/reset/",
            "/account/password/change/",
            "/account/password/set/",
        ):
            self.assertIn(self.client.get(path).status_code, (403, 404))

    def test_unsafe_login_return_is_replaced(self):
        response = self.client.get("/account/login/?next=https://attacker.example/")
        self.assertEqual(parse_qs(urlparse(response.url).query)["next"], ["/"])

    def test_unbound_legacy_session_must_reauthenticate(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/protected/").status_code, 302)

    def test_logout_ignores_next_and_local_only_options(self):
        self.binding()
        response = self.client.post(
            "/account/logout/?next=https://attacker.example/", {"range": "idp-only"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith(ISSUER + "/protocol/openid-connect/logout?")
        )
        query = parse_qs(urlparse(response.url).query)
        self.assertEqual(query["id_token_hint"], ["real-user-id-token"])
        self.assertEqual(query["post_logout_redirect_uri"], ["http://testserver/"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.binding(client)
        self.assertEqual(client.post("/account/logout/").status_code, 403)
        self.assertIn("_auth_user_id", client.session)

    def test_anonymous_landing_probes_once_and_rest_endpoints_do_not(self):
        response = self.client.get("/", HTTP_ACCEPT="text/html")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            parse_qs(urlparse(response.url).query)["auth_params"], ["prompt=none"]
        )
        self.assertEqual(self.client.get("/", HTTP_ACCEPT="text/html").status_code, 200)
        self.assertEqual(
            Client().get("/", HTTP_ACCEPT="application/json").status_code, 200
        )

    def test_oidc_login_registers_existing_user_without_changing_permissions(self):
        self.user.is_staff = True
        self.user.save()
        request = self.factory.get("/")
        request.session = SessionStore()
        request.session["repository_sso_pending"] = [
            {
                "iss": ISSUER,
                "sub": "keycloak-user",
                "sid": "sso-session",
                "iat": int(time.time()),
            },
            "user-id-token",
        ]
        login(request, self.user, backend="django.contrib.auth.backends.ModelBackend")
        binding = SessionBinding.objects.get(session_key=request.session.session_key)
        self.assertEqual(binding.subject, "keycloak-user")
        self.assertEqual(request.session["repository_sso_id_token"], "user-id-token")
        self.assertNotIn("repository_sso_pending", request.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)

    def test_session_resurrection_still_rejected(self):
        binding = self.binding()
        session = self.client.session
        old_data = dict(session)
        self.client.post("/sso/backchannel-logout/", {"logout_token": self.token()})
        restored = SessionStore(session_key=binding.session_key)
        restored.update(old_data)
        restored.save()
        self.assertEqual(self.client.get("/protected/").status_code, 302)

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
    def test_unsupported_session_engine_fails_configuration_check(self):
        self.assertIn("repository_sso.E001", [error.id for error in check_sso(None)])

    def test_oidc_token_and_userinfo_must_identify_same_subject(self):
        from allauth.socialaccount.providers.oauth2.client import OAuth2Error

        request = self.factory.get("/")
        request.session = SessionStore()
        adapter = SessionOIDCAdapter(request, "keycloak")
        raw = self.token(exp=int(time.time()) + 300)
        upstream = SimpleNamespace(
            account=SimpleNamespace(extra_data={"sub": "wrong-user"})
        )
        with patch(
            "allauth.socialaccount.providers.openid_connect.views.OpenIDConnectOAuth2Adapter.complete_login",
            return_value=upstream,
        ):
            with self.assertRaises(OAuth2Error):
                adapter.complete_login(
                    request,
                    SimpleNamespace(client_id="repository"),
                    None,
                    {"id_token": raw},
                )

    def test_expired_authority_check_refreshes_bound_session(self):
        from repository_sso.protocol import refresh_session

        binding = self.binding()
        request = self.factory.get("/protected/")
        request.session = self.client.session
        binding.check_after = 0
        binding.refresh_token = "user-refresh-token"
        binding.save()
        raw = self.token(exp=int(time.time()) + 300)
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {"id_token": raw, "refresh_token": "rotated-refresh"},
        )
        with patch(
            "repository_sso.protocol.requests.post", return_value=response
        ) as post:
            self.assertTrue(refresh_session(request, binding))
            self.assertEqual(
                post.call_args.kwargs["data"]["grant_type"], "refresh_token"
            )
        binding.refresh_from_db()
        self.assertEqual(binding.refresh_token, "rotated-refresh")

    def test_revoked_keycloak_refresh_ends_local_access(self):
        binding = self.binding()
        session = self.client.session
        SessionBinding.objects.filter(session_key=session.session_key).update(
            check_after=0, refresh_token="old-refresh"
        )
        session.save()
        response = SimpleNamespace(
            status_code=400, json=lambda: {"error": "invalid_grant"}
        )
        with patch("repository_sso.protocol.requests.post", return_value=response):
            self.assertEqual(self.client.get("/protected/").status_code, 302)
        binding.refresh_from_db()
        self.assertTrue(binding.revoked)

    def test_authority_outage_blocks_access_without_discarding_session(self):
        import requests

        self.binding()
        session = self.client.session
        SessionBinding.objects.filter(session_key=session.session_key).update(
            check_after=0, refresh_token="old-refresh"
        )
        session.save()
        with patch(
            "repository_sso.protocol.requests.post", side_effect=requests.Timeout()
        ):
            self.assertEqual(self.client.get("/protected/").status_code, 503)
        self.assertIn("_auth_user_id", self.client.session)

    def test_link_command_is_dry_run_and_preserves_account(self):
        from django.core.management import call_command
        from allauth.socialaccount.models import SocialAccount

        call_command(
            "link_keycloak_identity",
            user_id=str(self.user.pk),
            subject="vetted-subject",
            verbosity=0,
        )
        self.assertFalse(SocialAccount.objects.exists())
        call_command(
            "link_keycloak_identity",
            user_id=str(self.user.pk),
            subject="vetted-subject",
            apply=True,
            verbosity=0,
        )
        self.assertEqual(SocialAccount.objects.get().user_id, self.user.pk)
        self.assertTrue(self.user.check_password("local-password"))

    def test_link_command_refuses_identity_collision(self):
        from django.core.management import call_command, CommandError
        from allauth.socialaccount.models import SocialAccount

        other = get_user_model().objects.create_user(username="other")
        SocialAccount.objects.create(
            provider="keycloak", uid="vetted-subject", user=other
        )
        with self.assertRaises(CommandError):
            call_command(
                "link_keycloak_identity",
                user_id=str(self.user.pk),
                subject="vetted-subject",
                apply=True,
            )

    def test_stale_worker_binding_reuses_persisted_refresh_result(self):
        from repository_sso.protocol import refresh_session

        binding = self.binding()
        binding.check_after = 0
        binding.refresh_token = "original-refresh"
        binding.save()
        stale = SessionBinding.objects.get(pk=binding.pk)
        raw = self.token(exp=int(time.time()) + 300)
        response = SimpleNamespace(
            status_code=200, json=lambda: {"id_token": raw, "refresh_token": "rotated"}
        )
        request = self.factory.get("/")
        request.session = self.client.session
        with patch(
            "repository_sso.protocol.requests.post", return_value=response
        ) as post:
            self.assertTrue(refresh_session(request, binding))
            self.assertTrue(refresh_session(request, stale))
            self.assertEqual(post.call_count, 1)

    def test_initiating_logout_revokes_binding_before_idp_response(self):
        binding = self.binding()
        self.client.post("/account/logout/")
        binding.refresh_from_db()
        self.assertTrue(binding.revoked)
