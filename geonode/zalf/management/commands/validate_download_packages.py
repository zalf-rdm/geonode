"""
Validate the stored download packages (zalf-rdm/geonode#659).

`download_package_status` reports the build state recorded in the database.
This command asks the storage whether the file is actually there, which is the
only way to notice an object removed, truncated or never uploaded.
"""

import sys

from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import filesizeformat

from geonode.zalf import download_package_checks as checks
from geonode.zalf.download_packages import is_enabled
from geonode.zalf.models import DownloadPackage


class Command(BaseCommand):
    help = (
        "Check every download package against its storage: which are uploaded and available, "
        "and which are broken (object gone, size or checksum mismatch, unreadable ZIP, dead build)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--map", dest="map_ids", nargs="+", type=int, help="Only these map IDs")
        parser.add_argument(
            "--broken-only", action="store_true", help="Print only the rows needing attention, not the healthy ones"
        )
        parser.add_argument(
            "--missing",
            action="store_true",
            help="Also list published maps with no package at all (build them with build_download_packages)",
        )
        parser.add_argument(
            "--deep",
            action="store_true",
            help="Download each package and verify its sha256 and that the ZIP reads; slow and uses bandwidth",
        )
        parser.add_argument(
            "--max-deep-bytes",
            type=int,
            default=checks.DEFAULT_MAX_DEEP_BYTES,
            help=f"With --deep, skip packages larger than this (default {checks.DEFAULT_MAX_DEEP_BYTES})",
        )
        parser.add_argument(
            "--orphans",
            action="store_true",
            help="Also list objects under the prefix that no asset references, and assets no package references",
        )
        parser.add_argument(
            "--fail-on-broken",
            action="store_true",
            help="Exit 1 if anything is broken, for cron and monitoring",
        )

    def handle(
        self,
        *args,
        map_ids=None,
        broken_only=False,
        missing=False,
        deep=False,
        max_deep_bytes=None,
        orphans=False,
        fail_on_broken=False,
        **options,
    ):
        # Validation stays available while the feature is off: that is exactly when
        # someone wants to know what is still in the bucket before switching it on.
        if not is_enabled():
            self.stdout.write("Download packages are switched off (ZALF_DOWNLOAD_PACKAGE_ENABLED); checking anyway\n")

        results = checks.check_packages(
            map_ids=map_ids, include_missing=missing, deep=deep, max_deep_bytes=max_deep_bytes
        )
        if not results:
            self.stdout.write("No download packages to check")
            return

        shown = [result for result in results if result.is_broken] if broken_only else results
        self.stdout.write(f"{'MAP':>6}  {'STATUS':<12} {'STORED':>10}  WHERE / WHY")
        for result in shown:
            size = filesizeformat(result.stored_size) if result.stored_size else "-"
            style = self.style.SUCCESS if result.is_ok else self.style.ERROR if result.is_broken else self.style.WARNING
            self.stdout.write(f"{result.map_id:>6}  {style(f'{result.status:<12}')} {size:>10}  {result.map_title}")
            if result.location:
                self.stdout.write(f"{'':>8}{result.location}")
            if result.detail:
                self.stdout.write(f"{'':>8}{result.detail}")

        counts = checks.summarize(results)
        summary = ", ".join(f"{count} {status}" for status, count in counts.items())
        broken = sum(count for status, count in counts.items() if status in checks.BROKEN)
        self.stdout.write(f"\n{len(results)} packages checked: {summary}")

        if orphans:
            self._report_orphans()

        if broken:
            self.stdout.write(
                self.style.ERROR(f"{broken} package(s) need attention")
                + " -- rebuild them with: manage.py build_download_packages --map <ID>"
            )
            if fail_on_broken:
                sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("every package is available"))

    def _report_orphans(self):
        try:
            orphans, truncated = checks.find_orphans()
        except RuntimeError as error:
            raise CommandError(str(error))

        self.stdout.write("")
        if orphans:
            total = sum(orphan["size"] for orphan in orphans)
            self.stdout.write(
                self.style.WARNING(
                    f"{len(orphans)}{'+' if truncated else ''} object(s) in the bucket that no asset references, "
                    f"{filesizeformat(total)}:"
                )
            )
            for orphan in orphans:
                self.stdout.write(
                    f"{'':>8}{orphan['key']}  {filesizeformat(orphan['size'])}  "
                    f"{orphan['last_modified']:%Y-%m-%d %H:%M}"
                )
            self.stdout.write(f"{'':>8}Delete them with s3cmd once you have confirmed what they are.")
        else:
            self.stdout.write("No orphaned objects under the prefix")

        dangling = checks.find_dangling_assets()
        if dangling:
            self.stdout.write(
                self.style.WARNING(f"{len(dangling)} package asset(s) that no DownloadPackage row references:")
            )
            for asset in dangling:
                self.stdout.write(f"{'':>8}asset {asset.pk}: s3://{asset.bucket}/{asset.key}")
            self.stdout.write(f"{'':>8}Delete them under Zalf > S3 assets, which removes the object too.")
        else:
            self.stdout.write("No dangling package assets")

    # Kept so `--state`-style muscle memory from download_package_status fails loudly
    # rather than silently checking everything.
    def create_parser(self, *args, **kwargs):
        parser = super().create_parser(*args, **kwargs)
        parser.epilog = (
            f"States recorded in the database: {', '.join(state for state, _ in DownloadPackage.STATE_CHOICES)}. "
            "Use download_package_status for those; this command checks the storage."
        )
        return parser
