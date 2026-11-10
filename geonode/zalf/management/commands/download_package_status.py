"""
The state of every data collection's download package (zalf-rdm/geonode#659).

By default this asks the **storage**, not just the database: a `DownloadPackage`
row records what its last build concluded, so nothing in it notices an object
removed, truncated or never uploaded. `--db-only` skips that and reports the
rows alone, which is the cheap listing for when the bucket is slow, unreachable
or simply not the question.
"""

import sys

from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import filesizeformat

from geonode.zalf import download_package_checks as checks
from geonode.zalf.download_packages import is_enabled


class Command(BaseCommand):
    help = (
        "List the published data collections and the state of their download package, checked against the "
        "storage: which are available and which are broken (object gone, size or checksum mismatch, unreadable "
        "ZIP, a build whose worker died). Use --db-only for the database's own view."
    )

    def add_arguments(self, parser):
        parser.add_argument("--map", dest="map_ids", nargs="+", type=int, help="Only these map IDs")
        parser.add_argument(
            "--state",
            choices=checks.SEVERITY,
            nargs="+",
            help="Only packages in these states",
        )
        parser.add_argument(
            "--broken-only", action="store_true", help="Only the rows needing attention, not the healthy ones"
        )
        parser.add_argument(
            "--db-only",
            action="store_true",
            help="Do not ask the storage: report the recorded build state only. Fast, and works without credentials",
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
            "--fail-on-broken", action="store_true", help="Exit 1 if anything is broken, for cron and monitoring"
        )

    def handle(
        self,
        *args,
        map_ids=None,
        state=None,
        broken_only=False,
        db_only=False,
        deep=False,
        max_deep_bytes=None,
        orphans=False,
        fail_on_broken=False,
        **options,
    ):
        if db_only and (deep or orphans):
            raise CommandError("--db-only cannot be combined with --deep or --orphans: both need the storage")

        # Reporting stays available while the feature is off: that is exactly when
        # someone wants to know what is still in the bucket before switching it on.
        if not is_enabled():
            self.stdout.write("Download packages are switched off (ZALF_DOWNLOAD_PACKAGE_ENABLED); reporting anyway\n")

        results = checks.check_packages(
            map_ids=map_ids,
            # Published maps with no package are part of the answer to "what is the
            # state of the packages", so they are listed by default.
            include_missing=True,
            deep=deep,
            max_deep_bytes=max_deep_bytes,
            storage=not db_only,
        )
        if not results:
            # Not a reason to stop: orphans are exactly what is left once the
            # collections are gone, so --orphans still has something to say.
            self.stdout.write("No published data collections")
            if orphans:
                self._report_orphans()
            return

        shown = results
        if broken_only:
            shown = [result for result in shown if result.is_broken]
        if state:
            shown = [result for result in shown if result.status in state]

        if shown:
            self.stdout.write(f"{'ID':>6}  {'STATUS':<12} {'STORED':>10}  {'BUILT':<16}  TITLE")
        else:
            self.stdout.write("No packages need attention" if broken_only else "No packages match the given filters")
        for result in shown:
            size = filesizeformat(result.stored_size) if result.stored_size else "-"
            built = result.built_at.strftime("%Y-%m-%d %H:%M") if result.built_at else "-"
            style = self.style.SUCCESS if result.is_ok else self.style.ERROR if result.is_broken else self.style.WARNING
            self.stdout.write(
                f"{result.map_id:>6}  {style(f'{result.status:<12}')} {size:>10}  {built:<16}  {result.map_title}"
            )
            # The location and the reason only earn lines when there is something
            # to say. A healthy row is explained by its status; a clean check
            # leaves no detail, so a detail on an `ok` row is a real note (wrong
            # content type, or what --deep verified). --db-only's "the storage was
            # not asked" is stated once in the footer rather than on every row.
            if result.is_broken or (result.is_ok and result.detail):
                if result.location:
                    self.stdout.write(f"{'':>8}{result.location}")
                if result.detail:
                    self.stdout.write(f"{'':>8}{result.detail}")

        counts = checks.summarize(results)
        summary = ", ".join(f"{count} {status}" for status, count in counts.items())
        broken = sum(count for status, count in counts.items() if status in checks.BROKEN)
        # Counted over everything, so a filtered listing still gives the totals.
        self.stdout.write(f"\n{len(results)} published data collections: {summary}")
        if db_only:
            self.stdout.write("The storage was not asked (--db-only); 'ready' means the build said so")

        if orphans:
            self._report_orphans()

        if broken:
            self.stdout.write(
                self.style.ERROR(f"{broken} package(s) need attention")
                + " -- rebuild them with: manage.py build_download_packages --map <ID>"
            )
            if fail_on_broken:
                sys.exit(1)
        elif not db_only:
            self.stdout.write(self.style.SUCCESS("every package is available"))

    def _report_orphans(self):
        from django.conf import settings

        try:
            orphans, truncated = checks.find_orphans()
        except RuntimeError as error:
            raise CommandError(str(error))

        self.stdout.write("")
        if not settings.ZALF_DOWNLOAD_S3_PREFIX.strip("/"):
            # With no prefix the listing is the whole bucket. Fine for a bucket
            # of its own, dangerous in a shared one -- everything else in it
            # looks like an orphan, and the advice below is to delete orphans.
            self.stdout.write(
                self.style.WARNING(
                    "ZALF_DOWNLOAD_S3_PREFIX is empty, so this lists the whole bucket. If the bucket holds "
                    "anything besides download packages, what follows includes it. Check before deleting."
                )
            )
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
                self.stdout.write(f"{'':>8}asset {asset.pk}: {asset.report_location}")
            self.stdout.write(f"{'':>8}Delete them under Zalf > S3 assets, which removes the object too.")
        else:
            self.stdout.write("No dangling package assets")
