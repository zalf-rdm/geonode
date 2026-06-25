from geonode.zalf.api.views import (
    approve_data_collection_post,
    publish_data_collection,
    sync_metadata_view,
    datacite_metadata_view,
    datacite_prefixes_view,
)
from django.urls import re_path

urlpatterns = [
    re_path(r"^approve/(?P<mapid>\d+)/$", approve_data_collection_post, name="approve_data_collection"),
    re_path(r"^publish/(?P<mapid>\d+)/$", publish_data_collection, name="publish_data_collection"),
    re_path(r"^maps/(?P<mapid>\d+)/sync_metadata/$", sync_metadata_view, name="sync_metadata"),
    re_path(r"^datacite_metadata/(?P<pk>\d+)/$", datacite_metadata_view, name="datacite_metadata"),
    re_path(r"^datacite-prefixes/$", datacite_prefixes_view, name="datacite_prefixes"),
]
