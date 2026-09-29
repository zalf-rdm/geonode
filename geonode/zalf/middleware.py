import logging
from urllib.parse import urlparse

from django.conf import settings


logger = logging.getLogger(__name__)


def sso_cookie_domain():
    """Return the parent domain used by the repository applications."""
    site_url = getattr(settings, "SITE_URL", None) or getattr(settings, "SITEURL", "")
    host = urlparse(site_url).hostname or ""
    parts = host.split(".")

    if len(parts) <= 2:
        return host or None

    return f".{'.'.join(parts[1:])}"


class KeycloakSilentSSOMiddleware:
    """Maintain the cross-subdomain hint used to start an OIDC handoff."""

    cookie_name = "sso_hint"

    def __init__(self, get_response):
        self.get_response = get_response
        self.cookie_domain = sso_cookie_domain()

    def __call__(self, request):
        response = self.get_response(request)

        if self._is_logout(request):
            response.delete_cookie(
                self.cookie_name,
                domain=self.cookie_domain,
                path="/",
                samesite="Lax",
            )
        elif self._should_refresh_hint(request):
            response.set_cookie(
                self.cookie_name,
                "true",
                domain=self.cookie_domain,
                max_age=getattr(settings, "SESSION_COOKIE_AGE", 3600),
                samesite="Lax",
                path="/",
                secure=getattr(settings, "SESSION_COOKIE_SECURE", request.is_secure()),
                httponly=False,
            )

        return response

    def _is_logout(self, request):
        return (
            request.method == "POST"
            and "/account/logout/" in request.path
            and request.COOKIES.get(self.cookie_name) == "true"
        )

    @staticmethod
    def _should_refresh_hint(request):
        return request.user.is_authenticated and "text/html" in request.headers.get("Accept", "")
