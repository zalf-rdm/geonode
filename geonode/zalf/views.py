from django.shortcuts import get_object_or_404, redirect, render

from geonode.base.models import ResourceBase
from geonode.utils import resolve_object
from geonode.zalf.models import HighlightedCase, TrainingResource
from geonode.zalf.api.cms_utils import render_markdown


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
    return render(request, "zalf/trainings.html")


def cms_index(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())
    return render(request, "zalf/cms.html")
