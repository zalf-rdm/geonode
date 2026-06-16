from django.apps import AppConfig


class ZalfCmsConfig(AppConfig):
    name = "geonode.zalf_cms"
    verbose_name = "ZALF CMS"

    def ready(self):
        from django.db.models.signals import post_migrate
        from django.db.models.signals import post_save

        from django.contrib.auth import get_user_model

        from geonode.zalf_cms.initialization import bootstrap_zalf_cms, sync_staff_user_group

        post_migrate.connect(bootstrap_zalf_cms, sender=self)
        post_save.connect(sync_staff_user_group, sender=get_user_model())
