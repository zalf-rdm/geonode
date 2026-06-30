from django.urls import re_path

from geonode.zalf.api.views import (
    approve_data_collection_post,
    publish_data_collection,
    sync_metadata_view,
)
from geonode.zalf.api.cms_views import (
    HighlightedCaseListCreateView,
    HighlightedCaseDetailView,
    SpotlightBannerListCreateView,
    SpotlightBannerDetailView,
    TrainingResourceListCreateView,
    TrainingResourceDetailView,
    preview_markdown,
)

urlpatterns = [
    # Existing endpoints
    re_path(r"^approve/(?P<mapid>\d+)/$", approve_data_collection_post, name="approve_data_collection"),
    re_path(r"^publish/(?P<mapid>\d+)/$", publish_data_collection, name="publish_data_collection"),
    re_path(r"^maps/(?P<mapid>\d+)/sync_metadata/$", sync_metadata_view, name="sync_metadata"),

    # CMS — Highlighted Cases
    re_path(r"^cms/cases/$", HighlightedCaseListCreateView.as_view(), name="cms_cases"),
    re_path(r"^cms/cases/(?P<pk_or_slug>[\w-]+)/$", HighlightedCaseDetailView.as_view(), name="cms_case_detail"),

    # CMS — Spotlight Banners
    re_path(r"^cms/banners/$", SpotlightBannerListCreateView.as_view(), name="cms_banners"),
    re_path(r"^cms/banners/(?P<pk>\d+)/$", SpotlightBannerDetailView.as_view(), name="cms_banner_detail"),

    # CMS — Training Resources
    re_path(r"^cms/trainings/$", TrainingResourceListCreateView.as_view(), name="cms_trainings"),
    re_path(r"^cms/trainings/(?P<pk_or_slug>[\w-]+)/$", TrainingResourceDetailView.as_view(), name="cms_training_detail"),

    # Markdown preview (staff only)
    re_path(r"^cms/preview-markdown/$", preview_markdown, name="cms_preview_markdown"),
]
