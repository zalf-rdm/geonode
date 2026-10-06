import time

import jwt
from django.conf import settings
from django.http import HttpResponseNotFound
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2CallbackView,
    OAuth2LoginView,
)
from allauth.socialaccount.providers.oauth2.client import OAuth2Error
from allauth.socialaccount.providers.openid_connect.views import (
    OpenIDConnectOAuth2Adapter,
)

from .protocol import decode_token


class SessionOIDCAdapter(OpenIDConnectOAuth2Adapter):
    def complete_login(self, request, app, token, response, **kwargs):
        raw = response.get("id_token")
        try:
            claims = decode_token(raw, ["iss", "aud", "exp", "iat", "sub", "sid"])
            for name in ("sub", "sid"):
                if not isinstance(claims[name], str) or not claims[name] or len(claims[name]) > 255:
                    raise ValueError("Invalid identity")
            if claims.get("azp", app.client_id) != app.client_id:
                raise ValueError("Invalid authorized party")
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise OAuth2Error("Invalid Keycloak ID token") from exc
        login = super().complete_login(request, app, token, response=response, **kwargs)
        data = login.account.extra_data
        userinfo = data.get("userinfo", data)
        if userinfo.get("sub") != claims["sub"]:
            raise OAuth2Error("Userinfo subject differs from ID token")
        # Preserve both existing GeoNode flat claims and Upload Tool nested claims.
        data = {**claims, **userinfo, "id_token": claims, "userinfo": dict(userinfo)}
        login.account.extra_data = data
        request.repository_sso_identity = (claims, raw)
        request.session["repository_sso_pending"] = [claims, raw]
        request.session["repository_sso_refresh_token"] = response.get("refresh_token", "")
        request.session["repository_sso_check_after"] = min(time.time() + 60, claims["exp"] - 10)
        return login


def login(request, provider_id):
    if provider_id != settings.KEYCLOAK_SSO_PROVIDER_ID:
        return HttpResponseNotFound()
    return OAuth2LoginView.adapter_view(SessionOIDCAdapter(request, provider_id))(request)


def callback(request, provider_id):
    if provider_id != settings.KEYCLOAK_SSO_PROVIDER_ID:
        return HttpResponseNotFound()
    return OAuth2CallbackView.adapter_view(SessionOIDCAdapter(request, provider_id))(request)
