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
        parser.add_argument(
            "--errors",
            action="store_true",
            help="Only failed builds, each with the last line of its error (narrows to --state failed)",
        )

    def handle(self, *args, missing=False, state=None, errors=False, **options):
        packages = {package.map_id: package for package in DownloadPackage.objects.all()}
        counts = dict.fromkeys(STATES, 0)
        # --errors narrows the listing as well as adding detail. The name promises
        # "show me what went wrong", so on a healthy repository it has to print
        # nothing rather than every ready package.
        wanted = set(state) if state else set(STATES)
        if errors:
            wanted &= {DownloadPackage.STATE_FAILED}
        rows = []
        for map_obj in Map.objects.filter(is_published=True).order_by("id"):
            package = packages.get(map_obj.id)
            map_state = package.state if package else STATE_MISSING
            # Counted before filtering, so the summary always describes the whole
            # repository and not just the rows that were printed.
            counts[map_state] += 1
            if missing and package and package.is_ready:
                continue
            if map_state not in wanted:
                continue
            rows.append((map_obj, package, map_state))

        if rows:
            self.stdout.write(f"{'ID':>6}  {'STATE':<9} {'SIZE':>10}  {'BUILT':<16}  TITLE")
        else:
            self.stdout.write("No failed builds" if errors else "No maps match the given filters")
        for map_obj, package, map_state in rows:
            # A rebuild keeps serving the previous file, so show its size and date.
            size = filesizeformat(package.size) if package and package.asset_id and package.size else "-"
            built = package.built_at.strftime("%Y-%m-%d %H:%M") if package and package.built_at else "-"
            self.stdout.write(f"{map_obj.id:>6}  {map_state:<9} {size:>10}  {built:<16}  {map_obj.title}")
            if errors and map_state == DownloadPackage.STATE_FAILED:
                last_line = package.error.strip().splitlines()[-1] if package and package.error.strip() else None
                self.stdout.write(f"{'':>8}error: {last_line or 'none recorded'}")

        total = sum(counts.values())
        summary = ", ".join(f"{count} {name}" for name, count in counts.items() if count)
        self.stdout.write(f"\n{total} published maps: {summary or 'none'}")
        # Reporting stays available while the feature is off, so the state of
        # what was built earlier can still be inspected.
        if not is_enabled():
            self.stdout.write("Download packages are switched off (ZALF_DOWNLOAD_PACKAGE_ENABLED)")
