import logging

from django.conf import settings
from django.apps import AppConfig
from django.urls import include, re_path

logger = logging.getLogger(__name__)

class UploadAppConfig(AppConfig):
    name = "geonode.zalf"


    def run_setup_hooks(*args, **kwargs):
        from django.conf import settings
        from geonode.urls import urlpatterns

        urlpatterns += [
            re_path(r"^api/v2/", include("geonode.zalf.api.urls")),
        ]

    def ready(self):
        super().ready()
        logging.debug("Initialize ZALF module ...")
        self.run_setup_hooks()