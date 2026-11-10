from django.core.management.base import BaseCommand
from django.template.defaultfilters import filesizeformat

from geonode.maps.models import Map
from geonode.zalf.download_packages import is_enabled
from geonode.zalf.models import DownloadPackage

STATE_MISSING = "missing"
STATES = [STATE_MISSING] + [state for state, _ in DownloadPackage.STATE_CHOICES]


class Command(BaseCommand):
    help = (
        "List the published data collections and the state of their download package "
        "(zalf-rdm/geonode#659): missing, pending, building, ready or failed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--missing", action="store_true", help="Only maps without a ready package (as --missing-only builds them)"
        )
        parser.add_argument("--state", choices=STATES, nargs="+", help="Only maps in these states")
        parser.add_argument("--errors", action="store_true", help="Print the error of failed builds")

    def handle(self, *args, missing=False, state=None, errors=False, **options):
        packages = {package.map_id: package for package in DownloadPackage.objects.all()}
        counts = dict.fromkeys(STATES, 0)
        rows = []
        for map_obj in Map.objects.filter(is_published=True).order_by("id"):
            package = packages.get(map_obj.id)
            map_state = package.state if package else STATE_MISSING
            counts[map_state] += 1
            if missing and package and package.is_ready:
                continue
            if state and map_state not in state:
                continue
            rows.append((map_obj, package, map_state))

        self.stdout.write(f"{'ID':>6}  {'STATE':<9} {'SIZE':>10}  {'BUILT':<16}  TITLE")
        for map_obj, package, map_state in rows:
            # A rebuild keeps serving the previous file, so show its size and date.
            size = filesizeformat(package.size) if package and package.asset_id and package.size else "-"
            built = package.built_at.strftime("%Y-%m-%d %H:%M") if package and package.built_at else "-"
            self.stdout.write(f"{map_obj.id:>6}  {map_state:<9} {size:>10}  {built:<16}  {map_obj.title}")
            if errors and package and package.error and map_state == DownloadPackage.STATE_FAILED:
                self.stdout.write(f"{'':>8}error: {package.error.strip().splitlines()[-1]}")

        total = sum(counts.values())
        summary = ", ".join(f"{count} {name}" for name, count in counts.items() if count)
        self.stdout.write(f"\n{total} published maps: {summary or 'none'}")
        # Reporting stays available while the feature is off, so the state of
        # what was built earlier can still be inspected.
        if not is_enabled():
            self.stdout.write("Download packages are switched off (ZALF_DOWNLOAD_PACKAGE_ENABLED)")
