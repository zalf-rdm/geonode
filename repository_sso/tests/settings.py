"""Minimal Django integration harness, independent of GIS/database services."""

import os

SECRET_KEY = "integration-test-key-only"
DEBUG = True
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
ROOT_URLCONF = "repository_sso.tests.urls"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.openid_connect",
    "repository_sso",
]
SITE_ID = 1
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SSO_TEST_DB", ":memory:"),
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = os.environ.get("SSO_TEST_CLIENT", "repository") + "_session"
CSRF_COOKIE_NAME = os.environ.get("SSO_TEST_CLIENT", "repository") + "_csrf"
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "repository_sso.middleware.CentralSSOMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
KEYCLOAK_SSO_ENABLED = True
KEYCLOAK_SSO_ISSUER = os.environ.get("SSO_TEST_ISSUER", "https://identity.example/realms/repository")
KEYCLOAK_SSO_CLIENT_ID = os.environ.get("SSO_TEST_CLIENT", "repository")
KEYCLOAK_SSO_PROVIDER_ID = "keycloak"
KEYCLOAK_SSO_CLIENT_SECRET = "stub-secret"
KEYCLOAK_SSO_POST_LOGOUT_URL = os.environ.get("SSO_TEST_RETURN", "http://testserver/")
KEYCLOAK_SSO_LANDING_PATHS = ("/", "/catalogue/", "/pt/")
LOGIN_REDIRECT_URL = "/protected/"
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_ONLY = True
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_ADAPTER = "repository_sso.tests.adapter.TestSocialAdapter"
SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [
            {
                "provider_id": "keycloak",
                "name": "Keycloak",
                "client_id": KEYCLOAK_SSO_CLIENT_ID,
                "secret": "stub-secret",
                "settings": {"server_url": KEYCLOAK_SSO_ISSUER + "/.well-known/openid-configuration"},
            }
        ],
    }
}
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(__import__("pathlib").Path(__file__).parent / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "/static/"
