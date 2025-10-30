from geonode.upload.api.urls import urlpatterns
from geonode.zalf.api.views import approve_data_collection_post, publish_data_collection
from django.urls import re_path

urlpatterns = [
    re_path(r"^approve/(?P<mapid>\d+)/$", approve_data_collection_post, name="approve_data_collection"),
    # re_path(r"^(?P<mapid>[^/]+)?/approve$", approve_data_collection_get, name="approve_data_collection"),
    re_path(r"^publish/(?P<mapid>\d+)/$", publish_data_collection, name="publish_data_collection")
]