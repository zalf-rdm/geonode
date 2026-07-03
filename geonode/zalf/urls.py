from django.urls import include, re_path

from geonode.zalf.views import cms_index, case_detail, training_detail, trainings_list

urlpatterns = [
    re_path(r"^api/v2/", include("geonode.zalf.api.urls")),
    re_path(r"^cms/$", cms_index, name="cms_index"),
    re_path(r"^trainings/$", trainings_list, name="trainings_list"),
    re_path(r"^cases/(?P<slug>[\w-]+)/$", case_detail, name="case_detail"),
    re_path(r"^trainings/(?P<slug>[\w-]+)/$", training_detail, name="training_detail"),
]
