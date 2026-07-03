from django.apps import AppConfig


class DataPackageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "importer_datapackage"
    verbose_name = "Datapackage Importer"
