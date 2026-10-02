import logging

import jwt
from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import SessionBinding
from .protocol import logout_url, revoke_sessions, validate_logout_token

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def backchannel_logout(request):
    if not getattr(settings, "KEYCLOAK_SSO_ENABLED", False):
        return HttpResponse(status=404)
    raw = request.POST.get("logout_token", "")
    if not raw or len(raw) > 16384:
        return HttpResponseBadRequest("Invalid logout token")
    try:
        claims = validate_logout_token(raw)
    except jwt.PyJWKClientConnectionError:
        logger.warning("Cannot fetch Keycloak signing keys for logout")
        return HttpResponse("Keycloak signing keys unavailable", status=503)
    except (jwt.PyJWTError, ValueError, TypeError):
        return HttpResponseBadRequest("Invalid logout token")
    try:
        revoke_sessions(claims)
    except ValueError:
        return HttpResponseBadRequest("Invalid logout token")
    return HttpResponse(status=200)


def global_logout(request):
    if request.method == "GET":
        return render(request, "repository_sso/logout.html")
    if request.method != "POST":
        return HttpResponse(status=405)
    target = logout_url(request)
    SessionBinding.objects.filter(session_key=request.session.session_key).update(
        revoked=True
    )
    auth_logout(request)
    return HttpResponseRedirect(target)
