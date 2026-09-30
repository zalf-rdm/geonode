from collections import defaultdict
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch

from geonode.base.models import GeoKeyword, ResourceBase


def referenced_leaf_keywords(source="GADM"):
    """Return the most specific keyword(s) used by each resource.

    Uploads retain the complete GADM hierarchy. Only the deepest level is the
    resource's spatial association; treating an ancestor country as coverage
    would make a municipality-level dataset match every AOI in that country.
    """
    keywords = GeoKeyword.objects.filter(source__iexact=source).order_by("-level", "pk")
    resources = ResourceBase.objects.filter(geo_keywords__source__iexact=source).prefetch_related(
        Prefetch("geo_keywords", queryset=keywords)
    )
    leaves = {}
    for resource in resources.iterator(chunk_size=500):
        resource_keywords = list(resource.geo_keywords.all())
        if not resource_keywords:
            continue
        deepest_level = max(keyword.level for keyword in resource_keywords)
        for keyword in resource_keywords:
            if keyword.level == deepest_level:
                leaves[keyword.pk] = keyword
    return list(leaves.values())


def _as_multipolygon(geometry):
    if isinstance(geometry, Polygon):
        return MultiPolygon(geometry, srid=4326)
    if geometry.geom_type == "MultiPolygon":
        geometry.srid = 4326
        return geometry
    polygons = [part for part in geometry if part.geom_type == "Polygon"]
    if not polygons:
        raise ValueError(f"Expected polygonal GADM geometry, got {geometry.geom_type}.")
    return MultiPolygon(*polygons, srid=4326)


class Command(BaseCommand):
    help = "Populate shared GeoKeyword boundaries from an existing GADM GeoPackage."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path, help="Path to the GADM GeoPackage")
        parser.add_argument("--layer", help="Source layer when the GeoPackage contains multiple layers")
        parser.add_argument("--force", action="store_true", help="Replace boundaries that are already populated")

    def handle(self, *args, **options):
        try:
            from osgeo import ogr
        except ImportError as exc:
            raise CommandError("GDAL/OGR is required to read the GADM GeoPackage.") from exc

        source_path = options["source"].expanduser().resolve()
        if not source_path.is_file():
            raise CommandError(f"GADM source does not exist: {source_path}")

        keywords = referenced_leaf_keywords()
        if not options["force"]:
            keywords = [keyword for keyword in keywords if keyword.geometry is None]
        if not keywords:
            self.stdout.write(self.style.SUCCESS("All referenced GADM boundaries are already synchronized."))
            return

        dataset = ogr.Open(str(source_path), 0)
        if dataset is None:
            raise CommandError(f"Could not open GADM source: {source_path}")

        layer_names = [dataset.GetLayerByIndex(index).GetName() for index in range(dataset.GetLayerCount())]
        configured_layer = options.get("layer")
        if configured_layer and configured_layer not in layer_names:
            raise CommandError(f"Layer '{configured_layer}' not found. Available: {', '.join(layer_names)}")

        by_level = defaultdict(list)
        for keyword in keywords:
            by_level[keyword.level].append(keyword)

        synchronized = 0
        missing = []
        for level, level_keywords in sorted(by_level.items()):
            preferred_name = configured_layer or level_keywords[0].layer_name
            layer = dataset.GetLayerByName(preferred_name)
            if layer is None and len(layer_names) == 1:
                layer = dataset.GetLayerByName(layer_names[0])
            if layer is None:
                raise CommandError(
                    f"No layer for GADM level {level}. Expected '{preferred_name}', available: {', '.join(layer_names)}"
                )

            gid_field = f"GID_{level}"
            layer_definition = layer.GetLayerDefn()
            available_fields = [
                layer_definition.GetFieldDefn(index).GetName().upper()
                for index in range(layer_definition.GetFieldCount())
            ]
            if gid_field not in available_fields:
                raise CommandError(f"Layer '{layer.GetName()}' has no field {gid_field}.")

            wanted = {keyword.gid: keyword for keyword in level_keywords}
            quoted_gids = ", ".join("'" + gid.replace("'", "''") + "'" for gid in wanted)
            layer.SetAttributeFilter(f"{gid_field} IN ({quoted_gids})")
            geometries = {}
            for feature in layer:
                gid = feature.GetField(gid_field)
                ogr_geometry = feature.GetGeometryRef()
                if gid not in wanted or ogr_geometry is None:
                    continue
                part = GEOSGeometry(ogr_geometry.ExportToWkt(), srid=4326)
                geometries[gid] = part if gid not in geometries else geometries[gid].union(part)
            layer.SetAttributeFilter(None)
            layer.ResetReading()

            for gid, keyword in wanted.items():
                geometry = geometries.get(gid)
                if geometry is None:
                    missing.append(gid)
                    continue
                keyword.geometry = _as_multipolygon(geometry)
                keyword.save(update_fields=("geometry",))
                synchronized += 1

        self.stdout.write(self.style.SUCCESS(f"Synchronized {synchronized} shared GADM boundaries."))
        if missing:
            self.stdout.write(self.style.WARNING("No source feature found for: " + ", ".join(sorted(missing))))
