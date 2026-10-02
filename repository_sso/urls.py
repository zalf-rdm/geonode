from django.urls import path

from .views import backchannel_logout

urlpatterns = [
    path(
        "sso/backchannel-logout/",
        backchannel_logout,
        name="repository_sso_backchannel_logout",
    ),
]
