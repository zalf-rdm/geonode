"""OIDC callback extension for the repository's browser logout lifecycle."""

from urllib.parse import parse_qsl, urlencode

from allauth.socialaccount.providers.openid_connect.views import OpenIDConnectOAuth2Adapter
from allauth.socialaccount.providers.oauth2.views import OAuth2CallbackView, OAuth2LoginView

REAUTH_COOKIE = "zalf_oidc_reauthenticate"


def require_next_login(response, request):
    """Mark only the next explicit login, preserving normal cross-app SSO."""
    response.set_cookie(REAUTH_COOKIE, "1", secure=request.is_secure(), httponly=True, samesite="Lax", path="/")
    return response


class LogoutTokenAdapter(OpenIDConnectOAuth2Adapter):
    def complete_login(self, request, app, token, **kwargs):
        sociallogin = super().complete_login(request, app, token, **kwargs)
        request.session["oidc_login"] = True
        id_token = kwargs["response"].get("id_token")
        if id_token:
            # Keep the token in this browser session, never in a URL passed
            # between applications or in the user's permanent profile.
            request.session["oidc_id_token"] = id_token
        else:
            request.session.pop("oidc_id_token", None)
        return sociallogin


def oidc_login(request, provider_id):
    if request.COOKIES.get(REAUTH_COOKIE):
        params = dict(parse_qsl(request.GET.get("auth_params", "")))
        params["prompt"] = "login"
        request.GET = request.GET.copy()
        request.GET["auth_params"] = urlencode(params)
    return OAuth2LoginView.adapter_view(LogoutTokenAdapter(request, provider_id))(request)


def oidc_callback(request, provider_id):
    response = OAuth2CallbackView.adapter_view(LogoutTokenAdapter(request, provider_id))(request)
    if request.user.is_authenticated:
        response.delete_cookie(REAUTH_COOKIE, path="/", samesite="Lax")
    return response
