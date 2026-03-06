import logging
import os
import shutil

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

def _register_datacite_plugin():
    """
    Register the DataCite output schema plugin with pycsw.
    
    Copies pycsw_datacite.py from our catalogue backends into pycsw's
    installed outputschemas directory and adds 'datacite' to __all__.
    """
    try:
        import pycsw.plugins.outputschemas as outputschemas
        
        plugin_dir = os.path.dirname(outputschemas.__file__)
        target_path = os.path.join(plugin_dir, "datacite.py")
        
        # Copy our DataCite plugin if it doesn't already exist
        if not os.path.exists(target_path):
            source_path = os.path.join(
                os.path.dirname(__file__), "..", "catalogue", "backends", "pycsw_datacite.py"
            )
            source_path = os.path.normpath(source_path)
            if os.path.exists(source_path):
                shutil.copy2(source_path, target_path)
                logger.info(f"Installed DataCite output schema plugin to {target_path}")
            else:
                logger.warning(f"DataCite plugin source not found at {source_path}")
                return
        
        # Ensure 'datacite' is in __all__
        if 'datacite' not in outputschemas.__all__:
            outputschemas.__all__.append('datacite')
            logger.info("Registered 'datacite' in pycsw output schemas")
        
    except Exception as e:
        logger.warning(f"Failed to register DataCite pycsw plugin: {e}")

class UploadAppConfig(AppConfig):
    name = "geonode.zalf"

    def run_setup_hooks(*args, **kwargs):
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
        logging.debug("Initialize ZALF module ...")
        _register_datacite_plugin()
        self.run_setup_hooks()