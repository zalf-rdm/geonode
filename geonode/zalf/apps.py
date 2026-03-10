import logging

from django.apps import AppConfig
from django.urls import include, re_path

logger = logging.getLogger(__name__)


REQUIRED_DATACITE_SETTINGS = [
    "ZALF_DATACITE_BASE_URL",
    "ZALF_DATACITE_AGENT",
    "ZALF_DATACITE_USERNAME",
    "ZALF_DATACITE_PASSWORD",
]

class UploadAppConfig(AppConfig):
    name = "geonode.zalf"

    @staticmethod
    def run_setup_hooks():
        from django.conf import settings
        from geonode.urls import urlpatterns

        for required_setting in REQUIRED_DATACITE_SETTINGS:
            if not getattr(settings, required_setting, None):
                logger.warning(f"Setting '{required_setting}' is not configured for DOI registration")

        urlpatterns += [
            re_path(r"^api/v2/", include("geonode.zalf.api.urls")),
        ]

    def ready(self):
        super().ready()
        logger.debug("Initialize ZALF module ...")
        self.run_setup_hooks()