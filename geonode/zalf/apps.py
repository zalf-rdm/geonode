import logging

from django.apps import AppConfig
from django.urls import include, re_path

logger = logging.getLogger(__name__)


class UploadAppConfig(AppConfig):
    name = "geonode.zalf"

    @staticmethod
    def run_setup_hooks():
        from django.conf import settings
        from geonode.urls import urlpatterns

        if not getattr(settings, "ZALF_DATACITE_BASE_URL", None):
            logger.warning("Setting 'ZALF_DATACITE_BASE_URL' is not configured for DOI registration")
        if not getattr(settings, "ZALF_DATACITE_AGENT", None):
            logger.warning("Setting 'ZALF_DATACITE_AGENT' is not configured for DOI registration")

        accounts = getattr(settings, "ZALF_DATACITE_ACCOUNTS", [])
        if not accounts:
            logger.warning(
                "No DataCite accounts configured (ZALF_DATACITE_ACCOUNTS). " "DOI registration will not be available."
            )
        else:
            logger.info(f"Loaded {len(accounts)} DataCite account(s): {[a.get('username') for a in accounts]}")
            for i, acct in enumerate(accounts):
                if not acct.get("username") or not acct.get("password"):
                    logger.warning(f"DataCite account #{i} (username={acct.get('username')!r}) is missing credentials")
                if not acct.get("groups"):
                    logger.warning(
                        f"DataCite account #{i} (username={acct.get('username')!r}) has no groups assigned — "
                        "only admins will be able to use this account"
                    )

        urlpatterns += [
            re_path(r"^api/v2/", include("geonode.zalf.api.urls")),
        ]

    def ready(self):
        super().ready()
        logger.debug("Initialize ZALF module ...")
        self.run_setup_hooks()
