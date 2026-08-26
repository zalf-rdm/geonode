"""Backfill ISO scope codes into existing catalogue records.

Resources created before the scope codes were introduced have ``csw_type="dataset"`` and
a hardcoded ``dataset`` scope baked into their stored ISO XML; maps have never had their
XML generated at all. This command brings both up to date.

The upstream ``regenerate_xml`` command only walks ``Dataset.objects.all()``, so it
cannot repair maps -- hence a separate ZALF command rather than a patch to an upstream
file.
"""

import logging

from django.core.management.base import BaseCommand

from geonode.catalogue.models import catalogue_post_save
from geonode.layers.models import Dataset
from geonode.maps.models import Map
from geonode.zalf.catalogue import iso_scope_code, sync_csw_type

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-derive ISO scope codes (csw_type + metadata XML) for datasets and maps"

    def add_arguments(self, parser):
        parser.add_argument(
            "-d",
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Report what would change without writing anything",
        )
        parser.add_argument(
            "-i",
            "--id",
            dest="ids",
            type=int,
            action="append",
            help="Only process resources with the given id (repeatable)",
        )
        parser.add_argument(
            "-t",
            "--type",
            dest="types",
            choices=["dataset", "map"],
            action="append",
            help="Only process this resource type (repeatable; default: both)",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run")
        requested_ids = options.get("ids")
        requested_types = options.get("types") or ["dataset", "map"]

        querysets = []
        if "dataset" in requested_types:
            querysets.append(Dataset.objects.all().order_by("id"))
        if "map" in requested_types:
            querysets.append(Map.objects.all().order_by("id"))

        ok = skipped = failed = 0

        for queryset in querysets:
            if requested_ids:
                queryset = queryset.filter(id__in=requested_ids)

            for instance in queryset.iterator():
                scope_code = iso_scope_code(instance)
                label = f"{instance.resource_type} {instance.id} '{instance.title}' -> {scope_code}"

                # Same guard as the upstream regenerate_xml command: never clobber XML a
                # user uploaded and asked to keep.
                if instance.metadata_uploaded and instance.metadata_uploaded_preserve:
                    self.stdout.write(f"  skip (custom XML preserved): {label}")
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(f"  would update: {label}")
                    ok += 1
                    continue

                try:
                    sync_csw_type(instance)
                    catalogue_post_save(instance=instance, sender=instance.__class__)
                except Exception as exc:
                    self.stderr.write(f"  FAILED: {label}: {exc}")
                    logger.exception(f"Could not sync catalogue scope for resource {instance.id}")
                    failed += 1
                else:
                    self.stdout.write(f"  updated: {label}")
                    ok += 1

        summary = f"Processed: {ok}, skipped: {skipped}, failed: {failed}"
        self.stdout.write(self.style.SUCCESS(summary + (" [DRY RUN]" if dry_run else "")))
