import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .models import SessionBinding
from .protocol import (
    AuthorityUnavailable,
    is_local_admin_session,
    refresh_session,
    revocations_for,
)
from .views import global_logout


class CentralSSOMiddleware:
    """Require a live Keycloak binding for browser sessions and route auth centrally."""

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_admin_request(request):
        match = getattr(request, "resolver_match", None)
        if match is None:
            try:
                match = resolve(request.path_info)
            except Resolver404:
                return False
        return "admin" in match.namespaces

    def __call__(self, request):
        if getattr(settings, "KEYCLOAK_SSO_ENABLED", False):
            if request.session.get("_auth_user_id"):
                binding = SessionBinding.objects.filter(
                    session_key=request.session.session_key
                ).first()
                if not binding and (
                    is_local_admin_session(request) or self._is_admin_request(request)
                ):
                    # Django admin remains available to local staff/superusers.
                    # Their session is intentionally not linked to Keycloak and,
                    # once created by the admin login, is valid site-wide.
                    pass
                elif not binding or binding.revoked or revocations_for(binding).exists():
                    logout(request)
                elif request.path_info.endswith("/logout/"):
                    # Logout must remain available even during an IdP outage.
                    pass
                else:
                    try:
                        active = refresh_session(request, binding)
                    except AuthorityUnavailable:
                        return HttpResponse(
                            "Identity service temporarily unavailable.", status=503
                        )
                    if not active:
                        binding.revoked = True
                        binding.save(update_fields=["revoked"])
                        logout(request)
            elif request.session.get("repository_sso_id_token"):
                request.session.pop("repository_sso_id_token", None)
        return self.get_response(request)

    def login_redirect(self, request, passive=False):
        target = request.GET.get("next", settings.LOGIN_REDIRECT_URL)
        if not url_has_allowed_host_and_scheme(
            target, {request.get_host()}, require_https=request.is_secure()
        ):
            target = "/"
        params = {"next": target}
        if passive:
            target = request.get_full_path()
            request.session["repository_sso_probe"] = target
            request.session["repository_sso_probe_at"] = int(time.time())
            params = {"next": target, "auth_params": "prompt=none"}
        return HttpResponseRedirect(
            reverse(
                "openid_connect_login",
                kwargs={"provider_id": settings.KEYCLOAK_SSO_PROVIDER_ID},
            )
            + "?"
            + urlencode(params)
        )

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not getattr(settings, "KEYCLOAK_SSO_ENABLED", False):
            return None
        if self._is_admin_request(request):
            return None
        name = request.resolver_match.url_name
        if name == "repository_sso_backchannel_logout":
            return None
        if name in ("account_logout", "logout"):
            return global_logout(request)
        if name in ("account_login", "login", "dev_login", "account_ajax_login"):
            # Existing Kubernetes probes use the login route as a health check.
            # Return no login form or credentials flow to this GET-only probe.
            if (
                name == "account_login"
                and request.method == "GET"
                and request.headers.get("User-Agent", "").startswith("kube-probe/")
            ):
                return HttpResponse("OK")
            return self.login_redirect(request)
        if name in (
            "account_signup",
            "account_reset_password",
            "account_change_password",
            "account_set_password",
            "account_reset_password_from_key",
        ):
            return HttpResponseForbidden("Manage credentials through Keycloak.")
        if name in ("openid_connect_login", "openid_connect_callback"):
            if view_kwargs.get("provider_id") != settings.KEYCLOAK_SSO_PROVIDER_ID:
                return HttpResponseForbidden("Use the configured Keycloak provider.")
        if (
            request.method == "GET"
            and not request.user.is_authenticated
            and request.path_info in settings.KEYCLOAK_SSO_LANDING_PATHS
            and "text/html" in request.headers.get("Accept", "")
            and time.time() - request.session.get("repository_sso_probe_at", 0) > 60
        ):
            return self.login_redirect(request, passive=True)
        return None
