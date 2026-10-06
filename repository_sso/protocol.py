import hashlib
import time
from functools import lru_cache
from importlib import import_module
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q

from .models import LogoutEvent, SessionBinding

LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
# Marks a session created by the Django admin login, which has no Keycloak binding.
LOCAL_ADMIN_SESSION = "repository_sso_local_admin"


def is_local_admin_session(request):
    user = request.user
    return bool(
        request.session.get(LOCAL_ADMIN_SESSION) and user.is_active and user.is_staff
    )


@lru_cache(maxsize=8)
def signing_keys(issuer):
    # Never fetch URLs supplied by a token. Only the configured Keycloak realm.
    return jwt.PyJWKClient(
        issuer.rstrip("/") + "/protocol/openid-connect/certs", timeout=5
    )


def decode_token(raw, required):
    issuer = settings.KEYCLOAK_SSO_ISSUER
    key = signing_keys(issuer).get_signing_key_from_jwt(raw).key
    return jwt.decode(
        raw,
        key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=settings.KEYCLOAK_SSO_CLIENT_ID,
        options={"require": required},
        leeway=10,
    )


def validate_logout_token(raw):
    claims = decode_token(raw, ["iss", "aud", "iat", "jti", "events"])
    issued_at = claims["iat"]
    if isinstance(issued_at, bool) or not isinstance(issued_at, int):
        raise ValueError("Invalid issued-at claim")
    if issued_at < time.time() - 300 or issued_at > time.time() + 10:
        raise ValueError("Logout token outside allowed age")
    events = claims["events"]
    if not isinstance(events, dict) or events.get(LOGOUT_EVENT) != {}:
        raise ValueError("Missing logout event")
    if "nonce" in claims:
        raise ValueError("Logout tokens must not contain a nonce")
    for name in ("jti", "sid", "sub"):
        value = claims.get(name)
        if value is not None and (
            not isinstance(value, str) or not value or len(value) > 255
        ):
            raise ValueError("Invalid logout identifier")
    if not claims.get("sid") and not claims.get("sub"):
        raise ValueError("Logout must identify a subject or session")
    return claims


def revocations_for(binding):
    return LogoutEvent.objects.filter(
        issuer=binding.issuer,
    ).filter(
        Q(sid=binding.sid) & (Q(subject="") | Q(subject=binding.subject))
        | Q(sid="", subject=binding.subject, issued_at__gte=binding.issued_at)
    )


def revoke_sessions(claims):
    digest = hashlib.sha256((claims["iss"] + "\0" + claims["jti"]).encode()).hexdigest()
    with transaction.atomic():
        event, created = LogoutEvent.objects.get_or_create(
            digest=digest,
            defaults={
                "issuer": claims["iss"],
                "subject": claims.get("sub", ""),
                "sid": claims.get("sid", ""),
                "issued_at": claims["iat"],
            },
        )
        if not created:
            raise ValueError("Replayed logout token")
        bindings = SessionBinding.objects.filter(issuer=event.issuer)
        if event.sid:
            bindings = bindings.filter(sid=event.sid)
        if event.subject:
            bindings = bindings.filter(subject=event.subject)
        if not event.sid:
            bindings = bindings.filter(issued_at__lte=event.issued_at)
        keys = list(bindings.values_list("session_key", flat=True))
        bindings.update(revoked=True)
    store = import_module(settings.SESSION_ENGINE).SessionStore
    for key in keys:
        store(session_key=key).delete()


def logout_url(request):
    params = {
        "client_id": settings.KEYCLOAK_SSO_CLIENT_ID,
        "post_logout_redirect_uri": settings.KEYCLOAK_SSO_POST_LOGOUT_URL,
    }
    binding = SessionBinding.objects.filter(
        session_key=request.session.session_key
    ).first()
    token = (
        binding.id_token
        if binding and binding.id_token
        else request.session.get("repository_sso_id_token")
    )
    if token:
        params["id_token_hint"] = token
    return (
        settings.KEYCLOAK_SSO_ISSUER.rstrip("/")
        + "/protocol/openid-connect/logout?"
        + urlencode(params)
    )


class AuthorityUnavailable(Exception):
    pass


def refresh_session(request, binding):
    """Serialize refresh across workers; rotating tokens live in the binding row."""
    with transaction.atomic():
        current = SessionBinding.objects.select_for_update().get(
            session_key=binding.session_key
        )
        if current.revoked or revocations_for(current).exists():
            return False
        if time.time() < current.check_after:
            return True
        return refresh_binding(current)


def refresh_binding(binding):
    if not binding.refresh_token:
        return False
    try:
        response = requests.post(
            settings.KEYCLOAK_SSO_ISSUER.rstrip("/") + "/protocol/openid-connect/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": binding.refresh_token,
                "client_id": settings.KEYCLOAK_SSO_CLIENT_ID,
                "client_secret": settings.KEYCLOAK_SSO_CLIENT_SECRET,
            },
            timeout=5,
        )
        if (
            response.status_code == 400
            and response.json().get("error") == "invalid_grant"
        ):
            return False
        if response.status_code != 200:
            raise AuthorityUnavailable()
        data = response.json()
        raw = data["id_token"]
        claims = decode_token(raw, ["iss", "aud", "exp", "iat", "sub", "sid"])
        if claims["sub"] != binding.subject or claims["sid"] != binding.sid:
            return False
    except (
        requests.RequestException,
        jwt.PyJWTError,
        KeyError,
        ValueError,
        TypeError,
    ) as exc:
        raise AuthorityUnavailable() from exc
    binding.id_token = raw
    binding.refresh_token = data.get("refresh_token", binding.refresh_token)
    binding.check_after = int(min(time.time() + 60, claims["exp"] - 10))
    binding.save(update_fields=["id_token", "refresh_token", "check_after"])
    return not revocations_for(binding).exists()
