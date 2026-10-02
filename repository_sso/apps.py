from django.apps import AppConfig


class RepositorySSOConfig(AppConfig):
    name = "repository_sso"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import checks, signals  # noqa: F401
