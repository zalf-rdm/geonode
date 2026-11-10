from django.core.management.base import BaseCommand, CommandError

from geonode.maps.models import Map
from geonode.zalf.download_packages import is_enabled, request_build, run_build
from geonode.zalf.models import DownloadPackage


class Command(BaseCommand):
    help = (
        "Build the download package of published data collections (zalf-rdm/geonode#659). "
        "Queues Celery tasks unless --sync is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("--map", type=int, nargs="+", dest="map_ids", help="Map IDs to build")
        parser.add_argument("--all-published", action="store_true", help="Every published map")
        parser.add_argument(
            "--missing-only", action="store_true", help="With --all-published: skip maps whose package is ready"
        )
        parser.add_argument("--sync", action="store_true", help="Build in this process instead of queuing a task")

    def handle(self, *args, map_ids=None, all_published=False, missing_only=False, sync=False, **options):
        if not is_enabled():
            raise CommandError(
                "Download packages are switched off; set ZALF_DOWNLOAD_PACKAGE_ENABLED=True to build them"
            )
        if not map_ids and not all_published:
            raise CommandError("Give --map ID [ID ...] or --all-published")
        maps = Map.objects.filter(is_published=True)
        if map_ids:
            maps = maps.filter(id__in=map_ids)
            unpublished = set(map_ids) - set(maps.values_list("id", flat=True))
            if unpublished:
                self.stderr.write(f"Skipping unknown or unpublished maps: {sorted(unpublished)}")
        if missing_only:
            ready = DownloadPackage.objects.filter(state=DownloadPackage.STATE_READY, asset__isnull=False)
            maps = maps.exclude(id__in=ready.values("map_id"))

        for map_obj in maps.order_by("id"):
            if sync:
                DownloadPackage.objects.get_or_create(map=map_obj)
                package = run_build(map_obj.pk)
                self.stdout.write(f"Map {map_obj.pk}: {package.state} {package.error}".rstrip())
            else:
                package, started = request_build(map_obj)
                self.stdout.write(f"Map {map_obj.pk}: {'queued' if started else 'already ' + package.state}")
