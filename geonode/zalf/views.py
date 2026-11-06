from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation

from geonode.base.models import ResourceBase
from geonode.utils import resolve_object
from geonode.zalf.models import HighlightedCase, TrainingResource
from geonode.zalf.api.cms_utils import render_markdown

# The site's other languages (fr, es, it) fall back to the English setting:
# the operator publishes an imprint in German and English only. The German text
# remains the legally authoritative one.
IMPRINT_FALLBACK_LANGUAGE = "en"


def zalf_imprint_url(language=None):
    """
    The configured imprint URL for `language`, falling back to English.

    Read from settings on each call rather than captured at import: that keeps
    `override_settings` working in tests, and lets a deployment change the URL
    without the module having been imported at the right moment.
    """
    code = (language or translation.get_language() or IMPRINT_FALLBACK_LANGUAGE).split("-")[0].lower()
    urls = {
        "de": settings.ZALF_IMPRINT_URL_DE,
        "en": settings.ZALF_IMPRINT_URL_EN,
    }
    return urls.get(code) or urls[IMPRINT_FALLBACK_LANGUAGE]


def imprint(request):
    """
    Forward /imprint/ to the operator's imprint in the reader's language.

    Resolved per request rather than with a static RedirectView because the
    target depends on the active language, which LocaleMiddleware sets from the
    session, cookie or Accept-Language.

    Temporary (302) on purpose, for two reasons: a 301 is cached hard by
    browsers, so restoring a local imprint later would pin anyone who visited
    once to zalf.de; and a cached permanent redirect would also freeze the
    language chosen on the first visit.
    """
    return redirect(zalf_imprint_url(), permanent=False)


def landing_page_url(resource):
    """
    URL of the ZALF landing page of a resource. Uses the same type segments as the
    landing routes of the client (#/landing/<map|tabular-collection|dataset|document>/<pk>);
    tabular datasets are datasets. Other types have no landing page and keep their own page.
    """
    # resource_type can be empty for resources not created through the resource manager
    polymorphic_ctype = getattr(resource, "polymorphic_ctype", None)
    resource_type = resource.resource_type or (polymorphic_ctype.model if polymorphic_ctype else None)
    if resource_type == "map":
        segment = "tabular-collection" if resource.subtype == "tabular-collection" else "map"
    elif resource_type in ("dataset", "document"):
        segment = resource_type
    else:
        return resource.get_absolute_url()
    return f"/catalogue/#/landing/{segment}/{resource.pk}"


def resolve_landing_uuid(request, uuid):
    """
    /landing/<uuid>/ -> the landing page of the resource.

    Stable target for DOIs (zalf-rdm/geonode#823): GeoNode's /catalogue/uuid/<uuid>
    redirects to the viewer (for a data collection: the map), not to the landing page.
    Same permission check as /catalogue/uuid/<uuid>.
    """
    resource = resolve_object(request, ResourceBase, {"uuid": uuid})
    return redirect(landing_page_url(resource))


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
    """
    The training overview is only published while there is content (#850).

    With no active training resources the page is a bare shell — a heading over an
    empty grid — so it is hidden rather than shown empty. Adding resources in the
    CMS publishes it again; no code change is needed for that. `training_detail`
    already 404s for missing or inactive resources.
    """
    if not TrainingResource.objects.filter(is_active=True).exists():
        raise Http404("No active training resources.")
    return render(request, "zalf/trainings.html")


def cms_index(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())
    return render(request, "zalf/cms.html")
