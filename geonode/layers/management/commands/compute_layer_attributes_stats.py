"""
Management command to compute and store attribute statistics for GeoNode layers/datasets.
Supports both vector and raster datasets.
"""

import logging
from django.core.management.base import BaseCommand
from django.db.models import Q
from geonode.layers.models import Dataset
from geonode.geoserver.helpers import get_attribute_statistics, is_dataset_attribute_aggregable


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Compute and store attribute statistics for datasets"

    def add_arguments(self, parser):
        parser.add_argument("--dataset-id", type=int, default=None, help="Compute stats for a specific dataset ID")
        parser.add_argument("--all", action="store_true", help="Compute stats for all datasets")
        parser.add_argument("--force", action="store_true", help="Force recompute even if stats already exist")
        parser.add_argument(
            "--types",
            type=str,
            default="vector,raster",
            help="Comma-separated list of dataset types to process (vector, raster, all)",
        )

    def handle(self, *args, **options):
        dataset_id = options.get("dataset_id")
        force_recompute = options.get("force", False)
        types_str = options.get("types", "vector,raster")

        # Parse desired types
        if "all" in types_str.lower():
            desired_types = ["vector", "raster", "remote"]
        else:
            desired_types = [t.strip() for t in types_str.lower().split(",")]

        # Get datasets to process
        if dataset_id:
            datasets = Dataset.objects.filter(pk=dataset_id)
        else:
            # Get all datasets of specified types
            query = Q()
            for dtype in desired_types:
                query |= Q(subtype=dtype)
            datasets = Dataset.objects.filter(query)

        if not datasets.exists():
            self.stdout.write(self.style.WARNING("No datasets found matching criteria"))
            return

        total = datasets.count()
        self.stdout.write(f"Processing {total} dataset(s)...\n")

        processed = 0
        updated = 0
        skipped = 0

        # Map subtype to store_type
        store_type_map = {
            "vector": "dataStore",
            "vector_time": "dataStore",
            "tabular": "dataStore",
            "tileStore": "dataStore",
            "raster": "coverageStore",
            "remote": "remoteStore",
        }

        for dataset in datasets:
            self.stdout.write(f"[{processed+1}/{total}] {dataset.name} ({dataset.subtype})... ", ending="")

            attributes = dataset.attribute_set.all()
            if not attributes.exists():
                self.stdout.write(self.style.WARNING("No attributes"))
                skipped += 1
                processed += 1
                continue

            dataset_updated = False

            for attr in attributes:
                # Check if should skip based on existing stats
                has_stats = (
                    attr.count is not None or attr.min is not None or attr.max is not None or attr.average is not None
                )

                if has_stats and not force_recompute:
                    continue

                # Check if attribute is aggregable
                store_type = store_type_map.get(dataset.subtype, dataset.subtype)
                is_aggregable = is_dataset_attribute_aggregable(store_type, attr.attribute, attr.attribute_type)
                if not is_aggregable and store_type != "dataStore":
                    continue

                # Compute statistics
                try:
                    result = get_attribute_statistics(
                        dataset.alternate or dataset.typename,
                        attr.attribute,
                        store_type=store_type,
                        field_type=attr.attribute_type,
                    )

                    if result:
                        attr.count = result.get("Count")
                        attr.min = result.get("Min")
                        attr.max = result.get("Max")
                        attr.average = result.get("Average")
                        attr.median = result.get("Median")
                        attr.stddev = result.get("StandardDeviation")
                        attr.sum = result.get("Sum")
                        attr.unique_values = result.get("unique_values")

                        import datetime
                        from django.utils import timezone

                        attr.last_stats_updated = datetime.datetime.now(timezone.get_current_timezone())
                        attr.save()

                        dataset_updated = True
                        logger.debug(f"Updated stats for {dataset.name}.{attr.attribute}")
                except Exception as e:
                    logger.exception(f"Error computing stats for {dataset.name}.{attr.attribute}: {str(e)}")
                    continue

            if dataset_updated:
                updated += 1
                self.stdout.write(self.style.SUCCESS("UPDATED"))
            else:
                self.stdout.write("Skipped")
                skipped += 1

            processed += 1

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(f"Total processed: {processed}")
        self.stdout.write(f"Updated: {self.style.SUCCESS(updated)}")
        self.stdout.write(f"Skipped: {skipped}")
        self.stdout.write("=" * 60)
