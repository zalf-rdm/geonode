from django.conf import settings
from django.core.checks import Error, register


@register()
def check_sso(app_configs, **kwargs):
    if not getattr(settings, "KEYCLOAK_SSO_ENABLED", False):
        return []
    errors = []
    if settings.SESSION_ENGINE not in (
        "django.contrib.sessions.backends.db",
        "django.contrib.sessions.backends.cached_db",
    ):
        errors.append(
            Error(
                "Central SSO requires db or cached_db sessions.",
                id="repository_sso.E001",
            )
        )
    for name in (
        "KEYCLOAK_SSO_ISSUER",
        "KEYCLOAK_SSO_CLIENT_ID",
        "KEYCLOAK_SSO_PROVIDER_ID",
        "KEYCLOAK_SSO_CLIENT_SECRET",
    ):
        if not getattr(settings, name, None):
            errors.append(Error(f"{name} is required for central SSO.", id="repository_sso.E002"))
    from urllib.parse import urlparse

    for name in ("KEYCLOAK_SSO_ISSUER", "KEYCLOAK_SSO_POST_LOGOUT_URL"):
        value = urlparse(getattr(settings, name, ""))
        if value.scheme not in ("http", "https") or not value.netloc:
            errors.append(Error(f"{name} must be an absolute HTTP(S) URL.", id="repository_sso.E003"))
    return errors
