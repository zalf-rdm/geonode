from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from geonode.zalf.models import HighlightedCase, TrainingResource
from geonode.zalf.api.cms_utils import render_markdown
from geonode.zalf.oidc import require_next_login


def _identity_logout_url(request, redirect_url):
    """Build the Identity-e logout URL without exposing the ORCID login page."""
    end_session_url = getattr(settings, "SOCIALACCOUNT_PROVIDER_END_SESSION_URL", None)
    if not end_session_url:
        return redirect_url

    params = {}
    id_token = request.session.get("oidc_id_token")
    if id_token:
        params["id_token_hint"] = id_token
    elif (
        request.user.is_authenticated
        and (request.session.get("oidc_login") or getattr(settings, "SOCIALACCOUNT_ONLY", False))
        and getattr(settings, "SOCIALACCOUNT_CLIENT_ID", None)
    ):
        # Sessions created before id_token persistence was added still need to
        # terminate Identity-e. Keycloak may ask for confirmation in this
        # legacy fallback because no id_token_hint is available.
        params["client_id"] = settings.SOCIALACCOUNT_CLIENT_ID
    else:
        # A local Django login has no Identity-e session to terminate.
        return redirect_url

    params["post_logout_redirect_uri"] = redirect_url
    return f"{end_session_url}?{urlencode(params)}"


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def global_logout_start(request):
    """Send the browser through the Upload Tool before ending GeoNode SSO."""
    if request.method == "POST":
        upload_logout_url = getattr(settings, "UPLOAD_TOOL_GLOBAL_LOGOUT_URL", "")
        if upload_logout_url:
            return redirect(upload_logout_url)
        return redirect("global_logout_finalize")

    return render(
        request,
        "account/logout.html",
        {
            "global_logout_action_url": reverse("global_logout_start"),
            "auto_submit": request.headers.get("Sec-Fetch-Site") in {"same-origin", "same-site", "none"},
        },
    )


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def global_logout_finalize(request):
    """End the GeoNode session and then the shared Identity-e SSO session."""
    if request.method == "GET":
        return render(
            request,
            "account/logout_finalize.html",
            {
                "global_logout_action_url": reverse("global_logout_finalize"),
                "auto_submit": request.headers.get("Sec-Fetch-Site") in {"same-origin", "same-site", "none"},
            },
        )

    repository_home = settings.OIDC_POST_LOGOUT_REDIRECT_URL
    callback_url = getattr(settings, "UPLOAD_TOOL_GLOBAL_LOGOUT_COMPLETE_URL", "") or repository_home
    redirect_url = _identity_logout_url(request, callback_url)
    auth_logout(request)
    return require_next_login(redirect(redirect_url), request)


def case_detail(request, slug):
    obj = get_object_or_404(HighlightedCase, slug=slug, is_active=True)
    return render(
        request,
        "zalf/cms_detail.html",
        {
            "page_title": obj.title,
            "image_url": obj.image.url if obj.image else None,
            "body_html": render_markdown(obj.body_markdown),
            "back_href": "/",
            "back_label": "Back to home",
        },
    )


def training_detail(request, slug):
    obj = get_object_or_404(TrainingResource, slug=slug, is_active=True)
    return render(
        request,
        "zalf/cms_detail.html",
        {
            "page_title": obj.title,
            "page_subtitle": obj.organizer,
            "image_url": obj.thumbnail.url if obj.thumbnail else None,
            "body_html": render_markdown(obj.body_markdown),
            "back_href": "/trainings/",
            "back_label": "Back to trainings",
        },
    )


def trainings_list(request):
    return render(request, "zalf/trainings.html")


def cms_index(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())
    return render(request, "zalf/cms.html")
