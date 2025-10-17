import logging

from django.conf import settings
from django.apps import AppConfig
from django.urls import include, re_path

logger = logging.getLogger(__name__)

ZALF_DATACITE_BASE_URL = "ZALF_DATACITE_BASE_URL"
ZALF_DATACITE_AGENT = "ZALF_DATACITE_AGENT"
ZALF_DATACITE_USERNAME = "ZALF_DATACITE_USERNAME"
ZALF_DATACITE_PASSWORD = "ZALF_DATACITE_PASSWORD"

REQUIRED_DATACITE_SETTINGS = [
    ZALF_DATACITE_BASE_URL,
    ZALF_DATACITE_AGENT,
    ZALF_DATACITE_USERNAME,
    ZALF_DATACITE_PASSWORD,
]

class UploadAppConfig(AppConfig):
    name = "geonode.zalf"

    def run_setup_hooks(*args, **kwargs):
        from django.conf import settings
        from geonode.urls import urlpatterns

        for required_setting in REQUIRED_DATACITE_SETTINGS:
            if not getattr(settings, required_setting, None):
                logger.warning(f"Setting '{required_setting}' is required for DOI registration")

        urlpatterns += [
            re_path(r"^api/v2/", include("geonode.zalf.api.urls")),
        ]

    def ready(self):
        super().ready()
        logging.debug("Initialize ZALF module ...")
        self.run_setup_hooks()