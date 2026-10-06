"""Read-only delivery checks for newly published spatial datasets.

The audit intentionally does not rewrite styles or mutate GeoServer. Optional
seeding is isolated behind an explicit, bounded policy and is disabled by
default in settings.
"""

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from django.conf import settings
from django.db import connections
from guardian.shortcuts import get_anonymous_user
from requests.auth import HTTPBasicAuth

from geonode.geoserver.helpers import geofence, ogc_server_settings
from geonode.security.registry import permissions_registry


class DeliveryAuditUnavailable(Exception):
    """Transient dependency failure which Celery should retry."""


def _local_name(element):
    return element.tag.rsplit("}", 1)[-1]


def _children(element, name):
    return [child for child in element.iter() if _local_name(child) == name]


def _first_text(element, name, default=None):
    matches = _children(element, name)
    return matches[0].text.strip() if matches and matches[0].text else default


def _is_exception_body(response):
    prefix = response.content[:500].lstrip().lower()
    return b"serviceexception" in prefix or b"exceptionreport" in prefix or b"ows:exception" in prefix


def _web_mercator(lon, lat):
    lat = max(min(float(lat), 85.05112878), -85.05112878)
    x = float(lon) * 20037508.342789244 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    return x, y * 20037508.342789244 / 180.0


@dataclass
class Grid:
    name: str
    tile_width: int
    tile_height: int
    extent: tuple
    resolutions: tuple

    def aligned_tile(self, lon, lat, preferred_zoom):
        zoom = min(max(preferred_zoom, 0), len(self.resolutions) - 1)
        resolution = self.resolutions[zoom]
        span_x = resolution * self.tile_width
        span_y = resolution * self.tile_height
        x, y = _web_mercator(lon, lat)
        min_x, min_y, max_x, max_y = self.extent
        x = min(max(x, min_x), max_x - 1e-8)
        y = min(max(y, min_y), max_y - 1e-8)
        tile_x = math.floor((x - min_x) / span_x)
        tile_y = math.floor((y - min_y) / span_y)
        left = min_x + tile_x * span_x
        bottom = min_y + tile_y * span_y
        return zoom, (left, bottom, left + span_x, bottom + span_y)


class DatasetDeliveryAuditor:
    def __init__(self, dataset, session=None):
        self.dataset = dataset
        self.session = session or requests.Session()
        self.internal_url = ogc_server_settings.LOCATION.rstrip("/")
        self.public_url = ogc_server_settings.PUBLIC_LOCATION.rstrip("/")
        self.auth = HTTPBasicAuth(*ogc_server_settings.credentials)
        self.timeout = settings.ZALF_DELIVERY_AUDIT_REQUEST_TIMEOUT
        self.layer_name = f"{dataset.workspace}:{dataset.name}"
        self.checks = []

    def _record(self, name, passed, details=None, severity="error"):
        status = "passed" if passed else ("warning" if severity == "warning" else "failed")
        self.checks.append({"name": name, "status": status, "details": details or {}})
        return passed

    def _get(self, url, **kwargs):
        try:
            return self.session.get(url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise DeliveryAuditUnavailable(f"GET {url} failed: {exc}") from exc

    def _post(self, url, **kwargs):
        try:
            return self.session.post(url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise DeliveryAuditUnavailable(f"POST {url} failed: {exc}") from exc

    def check_permissions(self):
        anonymous = get_anonymous_user()
        guardian_perms = sorted(
            permissions_registry.get_perms(
                instance=self.dataset.get_self_resource(), user=anonymous, include_virtual=False
            )
        )
        guardian_public = "view_resourcebase" in guardian_perms

        if not settings.OGC_SERVER["default"].get("GEOFENCE_SECURITY_ENABLED", False):
            return self._record(
                "guardian_geofence",
                guardian_public,
                {"guardian_permissions": guardian_perms, "geofence_enabled": False},
                severity="warning",
            )

        try:
            payload = geofence.get_rules(
                workspace=self.dataset.workspace,
                workspace_any=False,
                layer=self.dataset.name,
                layer_any=False,
            )
        except Exception as exc:
            raise DeliveryAuditUnavailable(f"GeoFence rule lookup failed: {exc}") from exc

        rules = payload.get("rules", [])
        allow_services = {
            (rule.get("service") or "*").upper()
            for rule in rules
            if (rule.get("access") or "").upper() == "ALLOW" and not rule.get("userName") and not rule.get("roleName")
        }
        geofence_public = "*" in allow_services or {"WMS", "WFS"}.issubset(allow_services)
        return self._record(
            "guardian_geofence",
            guardian_public and geofence_public,
            {
                "guardian_permissions": guardian_perms,
                "geofence_rule_count": len(rules),
                "anonymous_allow_services": sorted(allow_services),
            },
        )

    def check_geoserver_layer(self):
        encoded_workspace = quote(self.dataset.workspace, safe="")
        encoded_name = quote(self.dataset.name, safe="")
        url = f"{self.internal_url}/rest/layers/{encoded_workspace}:{encoded_name}.xml"
        response = self._get(url, auth=self.auth)
        passed = response.status_code == 200 and not _is_exception_body(response)
        details = {"status_code": response.status_code}
        if passed:
            root = ET.fromstring(response.content)
            details.update(
                {
                    "enabled": _first_text(root, "enabled", "true") != "false",
                    "advertised": _first_text(root, "advertised", "true") != "false",
                }
            )
            passed = details["enabled"] and details["advertised"]
        return self._record("geoserver_layer", passed, details)

    def _grid(self, gridset_name):
        url = f"{self.internal_url}/gwc/rest/gridsets/{quote(gridset_name, safe='')}.xml"
        response = self._get(url, auth=self.auth)
        if response.status_code != 200 or _is_exception_body(response):
            return None, {"status_code": response.status_code, "gridset": gridset_name}
        root = ET.fromstring(response.content)
        coords = [float(item.text) for item in _children(root, "double") if item.text]
        resolutions_parent = _children(root, "resolutions")
        resolutions = []
        if resolutions_parent:
            resolutions = [float(item.text) for item in _children(resolutions_parent[0], "double") if item.text]
        if len(coords) < 4 or not resolutions:
            return None, {"gridset": gridset_name, "reason": "missing extent or resolutions"}
        return (
            Grid(
                name=gridset_name,
                tile_width=int(_first_text(root, "tileWidth", "256")),
                tile_height=int(_first_text(root, "tileHeight", "256")),
                extent=tuple(coords[:4]),
                resolutions=tuple(resolutions),
            ),
            {},
        )

    def check_gwc(self):
        url = f"{self.internal_url}/gwc/rest/layers/{quote(self.layer_name, safe='')}.xml"
        response = self._get(url, auth=self.auth)
        if response.status_code != 200 or _is_exception_body(response):
            self._record("gwc_configuration", False, {"status_code": response.status_code})
            return None

        root = ET.fromstring(response.content)
        gridset_names = [item.text.strip() for item in _children(root, "gridSetName") if item.text]
        formats = [item.text.strip() for parent in _children(root, "mimeFormats") for item in list(parent) if item.text]
        meta = [int(item.text) for parent in _children(root, "metaWidthHeight") for item in list(parent) if item.text]
        style_filters = []
        for node in root.iter():
            if _local_name(node).lower().endswith("parameterfilter") and _first_text(node, "key") == "STYLES":
                style_filters.append(
                    {
                        "type": _local_name(node),
                        "default": _first_text(node, "defaultValue", ""),
                        "values": [item.text or "" for item in _children(node, "string")],
                        "regex": _first_text(node, "regex"),
                    }
                )

        expected_grid = settings.ZALF_DELIVERY_AUDIT_GRIDSET
        expected_format = settings.ZALF_DELIVERY_AUDIT_FORMAT
        style = self.dataset.default_style.name if self.dataset.default_style else ""
        style_allowed = False
        for item in style_filters:
            values = item["values"]
            regex = item["regex"]
            style_allowed = style_allowed or item["default"] in ("", style) or style in values
            if regex:
                try:
                    style_allowed = style_allowed or bool(re.fullmatch(regex, style))
                except re.error:
                    pass

        grid, grid_error = self._grid(expected_grid) if expected_grid in gridset_names else (None, {})
        passed = all(
            [
                _first_text(root, "enabled", "true") != "false",
                expected_grid in gridset_names,
                expected_format in formats,
                meta == [settings.ZALF_DELIVERY_AUDIT_META_FACTOR] * 2,
                bool(style_filters) and style_allowed,
                grid is not None,
                grid.tile_width == settings.ZALF_DELIVERY_AUDIT_TILE_SIZE if grid else False,
                grid.tile_height == settings.ZALF_DELIVERY_AUDIT_TILE_SIZE if grid else False,
            ]
        )
        self._record(
            "gwc_configuration",
            passed,
            {
                "enabled": _first_text(root, "enabled", "true") != "false",
                "gridsets": gridset_names,
                "required_gridset": expected_grid,
                "formats": formats,
                "required_format": expected_format,
                "metatile": meta,
                "tile_size": [grid.tile_width, grid.tile_height] if grid else None,
                "style": style,
                "style_filters": style_filters,
                "grid_error": grid_error,
            },
        )
        return grid

    def check_anonymous_ows(self, grid):
        if not grid:
            self._record("anonymous_wms", False, {"reason": "no valid gridset"})
        else:
            ll_bbox = self.dataset.ll_bbox
            lon = (float(ll_bbox[0]) + float(ll_bbox[1])) / 2
            lat = (float(ll_bbox[2]) + float(ll_bbox[3])) / 2
            zoom, bbox = grid.aligned_tile(lon, lat, settings.ZALF_DELIVERY_AUDIT_TILE_ZOOM)
            wms_response = self._get(
                f"{self.public_url}/wms",
                params={
                    "SERVICE": "WMS",
                    "VERSION": "1.1.1",
                    "REQUEST": "GetMap",
                    "LAYERS": self.layer_name,
                    "STYLES": self.dataset.default_style.name if self.dataset.default_style else "",
                    "SRS": "EPSG:3857",
                    "BBOX": ",".join(f"{value:.12f}" for value in bbox),
                    "WIDTH": grid.tile_width,
                    "HEIGHT": grid.tile_height,
                    "FORMAT": settings.ZALF_DELIVERY_AUDIT_FORMAT,
                    "TILED": "true",
                },
            )
            cache_result = wms_response.headers.get("geowebcache-cache-result")
            content_type = wms_response.headers.get("content-type", "").lower()
            passed = (
                wms_response.status_code == 200
                and content_type.startswith("image/")
                and not _is_exception_body(wms_response)
                and cache_result in {"HIT", "MISS"}
            )
            self._record(
                "anonymous_wms",
                passed,
                {
                    "status_code": wms_response.status_code,
                    "content_type": content_type,
                    "cache_result": cache_result,
                    "gridset": grid.name,
                    "zoom": zoom,
                    "bbox": bbox,
                },
            )

        wfs_response = self._get(
            f"{self.public_url}/wfs",
            params={
                "SERVICE": "WFS",
                "VERSION": "1.0.0",
                "REQUEST": "GetFeature",
                "TYPENAME": self.layer_name,
                "OUTPUTFORMAT": "application/json",
                "MAXFEATURES": 1,
            },
        )
        content_type = wfs_response.headers.get("content-type", "").lower()
        passed = (
            wfs_response.status_code == 200
            and ("json" in content_type or wfs_response.content.lstrip().startswith(b"{"))
            and not _is_exception_body(wfs_response)
        )
        self._record(
            "anonymous_wfs",
            passed,
            {"status_code": wfs_response.status_code, "content_type": content_type},
        )

    def check_postgis(self):
        if not self.dataset.is_vector():
            return self._record("postgis", True, {"applicable": False, "subtype": self.dataset.subtype})

        alias = settings.OGC_SERVER["default"].get("DATASTORE") or "default"
        try:
            connection = connections[alias]
        except Exception as exc:
            return self._record("postgis", False, {"database_alias": alias, "error": str(exc)})

        table = self.dataset.name
        schema = "public"
        sample_limit = settings.ZALF_DELIVERY_AUDIT_GEOMETRY_SAMPLE
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT f_table_schema, f_geometry_column, srid, type "
                    "FROM geometry_columns WHERE f_table_name = %s ORDER BY f_table_schema = 'public' DESC LIMIT 1",
                    [table],
                )
                geometry = cursor.fetchone()
                if not geometry:
                    return self._record("postgis", False, {"reason": "geometry column not found", "table": table})
                schema, geometry_column, srid, geometry_type = geometry
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_index i "
                    "JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace "
                    "JOIN pg_am am ON am.oid=(SELECT relam FROM pg_class WHERE oid=i.indexrelid) "
                    "JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=ANY(i.indkey) "
                    "WHERE n.nspname=%s AND t.relname=%s AND a.attname=%s AND am.amname IN ('gist','spgist'))",
                    [schema, table, geometry_column],
                )
                spatial_index = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT c.reltuples::bigint, s.last_analyze, s.last_autoanalyze "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "LEFT JOIN pg_stat_all_tables s ON s.relid=c.oid "
                    "WHERE n.nspname=%s AND c.relname=%s",
                    [schema, table],
                )
                statistics = cursor.fetchone() or (None, None, None)

                quoted_table = f"{connection.ops.quote_name(schema)}.{connection.ops.quote_name(table)}"
                quoted_geometry = connection.ops.quote_name(geometry_column)
                cursor.execute(
                    f"SELECT count(*), max(ST_NPoints(g)), avg(ST_NPoints(g)) "
                    f"FROM (SELECT {quoted_geometry} AS g FROM {quoted_table} "
                    f"WHERE {quoted_geometry} IS NOT NULL LIMIT %s) sample",
                    [sample_limit],
                )
                sampled, max_points, avg_points = cursor.fetchone()
        except Exception as exc:
            return self._record("postgis", False, {"database_alias": alias, "error": str(exc)})

        analyzed = bool(statistics[1] or statistics[2])
        return self._record(
            "postgis",
            spatial_index and analyzed,
            {
                "database_alias": alias,
                "schema": schema,
                "table": table,
                "geometry_column": geometry_column,
                "geometry_type": geometry_type,
                "source_srid": srid,
                "viewer_srid": 3857,
                "reprojection_required": int(srid) != 3857,
                "spatial_index": spatial_index,
                "estimated_rows": statistics[0],
                "last_analyze": statistics[1].isoformat() if statistics[1] else None,
                "last_autoanalyze": statistics[2].isoformat() if statistics[2] else None,
                "sample_limit": sample_limit,
                "sampled_geometries": sampled,
                "sample_max_points": max_points,
                "sample_avg_points": float(avg_points) if avg_points is not None else None,
            },
        )

    def seed_if_enabled(self, grid):
        if not settings.ZALF_DELIVERY_AUDIT_SEED_ENABLED:
            return {"enabled": False, "reason": "disabled by policy"}
        if not grid:
            return {"enabled": True, "submitted": False, "reason": "invalid gridset"}

        min_zoom = settings.ZALF_DELIVERY_AUDIT_SEED_MIN_ZOOM
        max_zoom = settings.ZALF_DELIVERY_AUDIT_SEED_MAX_ZOOM
        max_tiles = settings.ZALF_DELIVERY_AUDIT_SEED_MAX_TILES
        if min_zoom < 0 or max_zoom < min_zoom or max_zoom >= len(grid.resolutions):
            return {"enabled": True, "submitted": False, "reason": "invalid zoom policy"}

        ll_bbox = self.dataset.ll_bbox
        low = _web_mercator(ll_bbox[0], ll_bbox[2])
        high = _web_mercator(ll_bbox[1], ll_bbox[3])
        bounds = (min(low[0], high[0]), min(low[1], high[1]), max(low[0], high[0]), max(low[1], high[1]))
        tile_count = 0
        for zoom in range(min_zoom, max_zoom + 1):
            span_x = grid.resolutions[zoom] * grid.tile_width
            span_y = grid.resolutions[zoom] * grid.tile_height
            tile_count += max(1, math.ceil((bounds[2] - bounds[0]) / span_x)) * max(
                1, math.ceil((bounds[3] - bounds[1]) / span_y)
            )
        if tile_count > max_tiles:
            return {
                "enabled": True,
                "submitted": False,
                "reason": "tile budget exceeded",
                "estimated_tiles": tile_count,
                "max_tiles": max_tiles,
            }

        payload = (
            "<seedRequest>"
            f"<name>{self.layer_name}</name><bounds><coords>"
            + "".join(f"<double>{value}</double>" for value in bounds)
            + "</coords></bounds>"
            f"<srs><number>3857</number></srs><zoomStart>{min_zoom}</zoomStart><zoomStop>{max_zoom}</zoomStop>"
            f"<format>{settings.ZALF_DELIVERY_AUDIT_FORMAT}</format><type>seed</type><threadCount>1</threadCount>"
            "</seedRequest>"
        )
        response = self._post(
            f"{self.internal_url}/gwc/rest/seed/{quote(self.layer_name, safe='')}.xml",
            data=payload,
            headers={"Content-Type": "text/xml"},
            auth=self.auth,
        )
        return {
            "enabled": True,
            "submitted": response.status_code in {200, 201},
            "status_code": response.status_code,
            "estimated_tiles": tile_count,
            "max_tiles": max_tiles,
            "bounds": bounds,
            "zoom": [min_zoom, max_zoom],
            "thread_count": 1,
        }

    def run(self):
        self.check_permissions()
        self.check_geoserver_layer()
        grid = self.check_gwc()
        self.check_anonymous_ows(grid)
        self.check_postgis()
        failed = [check["name"] for check in self.checks if check["status"] == "failed"]
        seed = self.seed_if_enabled(grid) if not failed else {"enabled": False, "reason": "audit failed"}
        return {
            "schema_version": 1,
            "dataset_id": self.dataset.pk,
            "layer": self.layer_name,
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed" if failed else "passed",
            "failed_checks": failed,
            "checks": self.checks,
            "seed": seed,
            "policy": {
                "style_mutation": False,
                "scale_denominator_mutation": False,
                "generalization_mutation": False,
            },
        }
