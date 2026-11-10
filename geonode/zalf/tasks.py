from django.conf import settings

from geonode.celery_app import app


@app.task(
    bind=True,
    name="geonode.zalf.tasks.build_download_package",
    queue="zalf.download_package",
    ignore_result=True,
    time_limit=settings.ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT,
    soft_time_limit=settings.ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT - 60,
)
def build_download_package(self, map_id):
    """Builds and stores the download package of a map (zalf-rdm/geonode#659)."""
    from geonode.zalf.download_packages import run_build

    run_build(map_id, task_id=self.request.id or "")
