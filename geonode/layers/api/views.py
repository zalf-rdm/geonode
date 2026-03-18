#########################################################################
#
# Copyright (C) 2020 OSGeo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################
from drf_spectacular.utils import extend_schema

from dynamic_rest.viewsets import DynamicModelViewSet
from dynamic_rest.filters import DynamicFilterBackend, DynamicSortingFilter

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.response import Response

from geonode.base.api.filters import DynamicSearchFilter, ExtentFilter
from geonode.base.api.mixins import AdvertisedListMixin
from geonode.base.api.pagination import GeoNodeApiPagination
from geonode.base.api.permissions import UserHasPerms
from geonode.base.api.views import ApiPresetsInitializer
from geonode.layers.api.exceptions import GeneralDatasetException, InvalidDatasetException, InvalidMetadataException
from geonode.layers.metadata import parse_metadata
from geonode.layers.models import Dataset, Attribute
from geonode.geoserver.helpers import get_attribute_statistics, is_dataset_attribute_aggregable
from geonode.maps.api.serializers import SimpleMapLayerSerializer, SimpleMapSerializer
from geonode.resource.utils import update_resource
from geonode.resource.manager import resource_manager
from rest_framework.exceptions import NotFound, ValidationError

from geonode.storage.manager import StorageManager

from .serializers import (
    DatasetSerializer,
    DatasetListSerializer,
    DatasetMetadataSerializer,
)
from .permissions import DatasetPermissionsFilter

import logging
import re
import json
from datetime import datetime

logger = logging.getLogger(__name__)

NUMERIC_TYPE_RE = re.compile(r"(int|integer|float|double|decimal|numeric|number)", re.IGNORECASE)
DATE_TYPE_RE = re.compile(r"xsd:(date|dateTime)", re.IGNORECASE)
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d.%m.%y",
]


def _get_store_type(subtype):
    return {
        "vector": "dataStore",
        "vector_time": "dataStore",
        "tabular": "dataStore",
        "tileStore": "dataStore",
        "raster": "coverageStore",
        "remote": "remoteStore",
    }.get(subtype, subtype)


def _has_any_stats(attr):
    return any(
        [
            _parse_stat(attr.min) is not None,
            _parse_stat(attr.max) is not None,
            _parse_stat(attr.average) is not None,
            _parse_stat(attr.median) is not None,
            _parse_stat(attr.stddev) is not None,
            _parse_stat(attr.sum) is not None,
            bool(attr.unique_values and attr.unique_values not in ("", "NA")),
        ]
    )


def _needs_attribute_stats_refresh(attr):
    unique_values = (attr.unique_values or "").strip() if isinstance(attr.unique_values, str) else ""
    has_legacy_unique_values = bool(unique_values and unique_values not in ("NA", "") and not unique_values.startswith("["))
    numeric_stats_missing = all(
        [
            _parse_stat(attr.min) is None,
            _parse_stat(attr.max) is None,
            _parse_stat(attr.average) is None,
            _parse_stat(attr.median) is None,
            _parse_stat(attr.stddev) is None,
            _parse_stat(attr.sum) is None,
        ]
    )
    return has_legacy_unique_values and (
        numeric_stats_missing or (attr.attribute_type or "").lower() in ("xsd:string", "xsd:int", "xsd:double")
    )


def _backfill_attribute_stats(dataset, attr):
    """Compute and persist missing stats on demand for a single attribute."""
    store_type = _get_store_type(dataset.subtype)
    is_aggregable = is_dataset_attribute_aggregable(store_type, attr.attribute, attr.attribute_type)
    # For vectors/tabular datasets we also backfill non-numeric fields to expose
    # useful summaries (count + unique values / geometry types).
    if not is_aggregable and store_type != "dataStore":
        return attr

    result = get_attribute_statistics(
        dataset.alternate or dataset.typename,
        attr.attribute,
        store_type=store_type,
        field_type=attr.attribute_type,
    )
    if not result:
        return attr

    attr.count = result.get("Count")
    attr.min = result.get("Min")
    attr.max = result.get("Max")
    attr.average = result.get("Average")
    attr.median = result.get("Median")
    attr.stddev = result.get("StandardDeviation")
    attr.sum = result.get("Sum")
    attr.unique_values = result.get("unique_values")
    inferred_field_type = result.get("inferred_field_type")
    if inferred_field_type:
        attr.attribute_type = inferred_field_type
    attr.save()
    return attr


def _parse_stat(value, as_float=True):
    """Convert a stored stat string to float or None."""
    if value in (None, "NA", ""):
        return None
    try:
        return float(value) if as_float else value
    except (ValueError, TypeError):
        return None


def _to_number(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


def _parse_date_value(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _infer_attribute_type(attribute_type, raw_unique_values, min_val=None, max_val=None):
    current = attribute_type or "xsd:string"
    if NUMERIC_TYPE_RE.search(current) or DATE_TYPE_RE.search(current):
        return current

    numeric_markers = [_to_number(min_val), _to_number(max_val)]
    if any(v is not None for v in numeric_markers):
        return "xsd:double"

    if not raw_unique_values:
        return current

    sample = raw_unique_values[:50]
    numeric_count = sum(1 for v in sample if _to_number(v) is not None)
    date_count = sum(1 for v in sample if _parse_date_value(v) is not None)
    size = len(sample)

    if size and (numeric_count / size) >= 0.8:
        numeric_values = [_to_number(v) for v in sample]
        numeric_values = [v for v in numeric_values if v is not None]
        if numeric_values and all(float(v).is_integer() for v in numeric_values):
            return "xsd:int"
        return "xsd:double"

    if size and (date_count / size) >= 0.8:
        has_time = any((str(v).find("T") > -1 or str(v).find(":") > -1) for v in sample)
        return "xsd:dateTime" if has_time else "xsd:date"

    return current


def _build_attribute_stats(attr):
    """Build a structured stats dict from an Attribute model instance."""
    min_stat = _parse_stat(attr.min)
    max_stat = _parse_stat(attr.max)

    # Parse unique_values into a sorted list (stored as comma-separated string)
    raw_unique = []
    unique_vals = None
    total_unique = None
    if attr.unique_values and attr.unique_values not in ("NA", ""):
        parsed_json = None
        if isinstance(attr.unique_values, str):
            text = attr.unique_values.strip()
            if text.startswith("["):
                try:
                    parsed_json = json.loads(text)
                except json.JSONDecodeError:
                    parsed_json = None

        if isinstance(parsed_json, list):
            raw_unique = [str(v).strip() for v in parsed_json if str(v).strip()]
        else:
            raw_unique = [v.strip() for v in attr.unique_values.split(",") if v.strip()]

    effective_type = _infer_attribute_type(attr.attribute_type, raw_unique, attr.min, attr.max)
    is_numeric = NUMERIC_TYPE_RE.search(effective_type) is not None
    is_date = DATE_TYPE_RE.search(effective_type) is not None

    if raw_unique:
        total_unique = len(set(raw_unique))
        if is_numeric:
            parsed = []
            for v in raw_unique:
                num = _to_number(v)
                if num is not None:
                    parsed.append(num)
            unique_vals = sorted(parsed) if parsed else None
        elif is_date:
            parsed = [(value, _parse_date_value(value)) for value in raw_unique]
            parsed = [item for item in parsed if item[1] is not None]
            parsed = sorted(parsed, key=lambda item: item[1])
            unique_vals = [value for value, _ in parsed][:50] if parsed else None
        else:
            unique_vals = sorted(set(raw_unique))[:50]  # cap at 50 for strings

    if is_date and (min_stat is None or max_stat is None) and raw_unique:
        parsed_dates = [_parse_date_value(v) for v in raw_unique]
        parsed_dates = [d for d in parsed_dates if d is not None]
        if parsed_dates:
            min_stat = min(parsed_dates).date().isoformat()
            max_stat = max(parsed_dates).date().isoformat()

    if is_numeric and unique_vals:
        if min_stat is None:
            min_stat = min(unique_vals)
        if max_stat is None:
            max_stat = max(unique_vals)

    # Build histogram bins from unique numeric values if available
    histogram = None
    histogram_estimated = False
    if is_numeric and unique_vals and len(unique_vals) >= 2:
        mn = _parse_stat(attr.min) if _parse_stat(attr.min) is not None else min(unique_vals)
        mx = _parse_stat(attr.max) if _parse_stat(attr.max) is not None else max(unique_vals)
        if mn is not None and mx is not None and mx > mn:
            bin_count = min(10, len(unique_vals))
            bin_size = (mx - mn) / bin_count
            bins = []
            for i in range(bin_count):
                low = mn + i * bin_size
                high = mn + (i + 1) * bin_size
                count = sum(1 for v in unique_vals if low <= v < high)
                bins.append({"range": [round(low, 4), round(high, 4)], "count": count})
            histogram = bins

    # Fallback for numeric layers (e.g. raster) when we only have range/count.
    # This provides an estimated distribution instead of no chart at all.
    if histogram is None and is_numeric:
        mn = _parse_stat(attr.min) if _parse_stat(attr.min) is not None else (min(unique_vals) if unique_vals else None)
        mx = _parse_stat(attr.max) if _parse_stat(attr.max) is not None else (max(unique_vals) if unique_vals else None)
        total_count = int(attr.count or 0)
        if mn is not None and mx is not None and mx > mn:
            bin_count = 10
            bin_size = (mx - mn) / bin_count
            base = total_count // bin_count if total_count > 0 else 0
            remainder = total_count % bin_count if total_count > 0 else 0
            bins = []
            for i in range(bin_count):
                low = mn + i * bin_size
                high = mn + (i + 1) * bin_size
                estimated_count = base + (1 if i < remainder else 0)
                bins.append({"range": [round(low, 4), round(high, 4)], "count": estimated_count})
            histogram = bins
            histogram_estimated = True

    return {
        "attribute": attr.attribute,
        "attribute_label": attr.attribute_label,
        "attribute_type": effective_type,
        "attribute_unit": attr.attribute_unit,
        "count": attr.count,
        "min": min_stat,
        "max": max_stat,
        "mean": _parse_stat(attr.average),
        "median": _parse_stat(attr.median),
        "stddev": _parse_stat(attr.stddev),
        "sum": _parse_stat(attr.sum),
        "unique_values": unique_vals,
        "total_unique": total_unique,
        "groups": None,
        "histogram": histogram,
        "histogram_estimated": histogram_estimated,
        "last_stats_updated": attr.last_stats_updated,
        "has_stats": is_numeric or (unique_vals is not None),
    }


class DatasetViewSet(ApiPresetsInitializer, DynamicModelViewSet, AdvertisedListMixin):
    """
    API endpoint that allows layers to be viewed or edited.
    """

    http_method_names = ["get", "patch", "put"]
    authentication_classes = [SessionAuthentication, BasicAuthentication, OAuth2Authentication]
    permission_classes = [
        IsAuthenticatedOrReadOnly,
        UserHasPerms(perms_dict={"default": {"POST": ["base.add_resourcebase"]}}),
    ]
    filter_backends = [
        DynamicFilterBackend,
        DynamicSortingFilter,
        DynamicSearchFilter,
        ExtentFilter,
        DatasetPermissionsFilter,
    ]
    queryset = Dataset.objects.all().order_by("-created")
    serializer_class = DatasetSerializer
    pagination_class = GeoNodeApiPagination

    def get_serializer_class(self):
        if self.action == "list":
            return DatasetListSerializer
        return DatasetSerializer

    def partial_update(self, request, *args, **kwargs):
        dataset = self.get_object()
        attribute_data = request.data.get("attribute", [])

        for attr in attribute_data:
            pk = attr.get("pk")
            try:
                instance = dataset.attribute_set.get(pk=pk)
                from .serializers import AttributeSerializer

                serializer = AttributeSerializer(instance, data=attr, partial=True)
                if serializer.is_valid():
                    serializer.save()

            except Exception as e:
                logging.error(f"Error updating attribute {pk}: {e}")

        result = super().partial_update(request, *args, **kwargs)

        dataset = self.get_object()
        resource_manager.update(dataset.uuid, instance=dataset, notify=True),

        return result

    @extend_schema(
        request=DatasetMetadataSerializer,
        methods=["put"],
        responses={200},
        description="API endpoint to upload metadata file.",
    )
    @action(
        detail=False,
        url_path="(?P<pk>\d+)/metadata",  # noqa
        url_name="replace-metadata",
        methods=["put"],
        serializer_class=DatasetMetadataSerializer,
        permission_classes=[
            IsAuthenticated,
            UserHasPerms(perms_dict={"default": {"PUT": ["base.change_resourcebase_metadata"]}}),
        ],
    )
    def metadata(self, request, pk=None, *args, **kwargs):
        """
        Endpoint to upload ISO metadata
        Usage Example:

        import requests

        dataset_id = 1
        url = f"http://localhost:8080/api/v2/datasets/{dataset_id}/metadata"
        files=[
            ('metadata_file',('metadata.xml',open('/home/user/metadata.xml','rb'),'text/xml'))
        ]
        headers = {
            'Authorization': 'Basic dXNlcjpwYXNzd29yZA=='
        }
        response = requests.request("PUT", url, payload={}, files=files)

        cURL example:
        curl --location --request PUT 'http://localhost:8000/api/v2/datasets/{dataset_id}/metadata' \
        --form 'metadata_file=@/home/user/metadata.xml'
        """
        out = {}
        storage_manager = None
        if not self.queryset.filter(id=pk).exists():
            raise NotFound(detail=f"Dataset with ID {pk} is not available")
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid(raise_exception=False):
            raise InvalidDatasetException(detail=serializer.errors)
        try:
            data = serializer.data.copy()
            if not data["metadata_file"]:
                raise InvalidMetadataException(detail="A valid metadata file must be specified")
            storage_manager = StorageManager(remote_files=data)
            storage_manager.clone_remote_files()
            file = storage_manager.get_retrieved_paths()
            metadata_file = file["metadata_file"]
            dataset = self.queryset.get(id=pk)
            try:
                dataset_uuid, vals, regions, keywords, _ = parse_metadata(open(metadata_file).read())
            except Exception:
                raise InvalidMetadataException(detail="Unsupported metadata format")
            if dataset_uuid and dataset.uuid != dataset_uuid:
                raise InvalidMetadataException(
                    detail="The UUID identifier from the XML Metadata, is different from the one saved"
                )
            try:
                updated_dataset = update_resource(dataset, metadata_file, regions, keywords, vals)
                updated_dataset.save()  # This also triggers the recreation of the XML metadata file according to the updated values
            except Exception:
                raise GeneralDatasetException(detail="Failed to update metadata")
            out["success"] = True
            out["message"] = ["Metadata successfully updated"]
            return Response(out)
        except Exception as e:
            raise e
        finally:
            if storage_manager:
                storage_manager.delete_retrieved_paths()

    @extend_schema(
        methods=["get"],
        responses={200: SimpleMapLayerSerializer(many=True)},
        description="API endpoint allowing to retrieve the MapLayers list.",
    )
    @action(detail=True, methods=["get"])
    def maplayers(self, request, pk=None, *args, **kwargs):
        dataset = self.get_object()
        resources = dataset.maplayers
        return Response(SimpleMapLayerSerializer(many=True).to_representation(resources))

    @extend_schema(
        methods=["get"],
        responses={200: SimpleMapSerializer(many=True)},
        description="API endpoint allowing to retrieve maps using the dataset.",
    )
    @action(detail=True, methods=["get"])
    def maps(self, request, pk=None, *args, **kwargs):
        dataset = self.get_object()
        resources = dataset.maps
        return Response(SimpleMapSerializer(many=True).to_representation(resources))

    @extend_schema(
        methods=["get"],
        responses={200},
        description=(
            "Returns pre-computed statistics for all attributes of the dataset, or a single "
            "attribute when the `attribute` query param is provided (e.g. ?attribute=SOIL_TEMP). "
            "Stats are sourced from the Attribute model fields populated during dataset ingestion."
        ),
    )
    @action(detail=True, methods=["get"], url_path="attribute_stats", url_name="attribute-stats")
    def attribute_stats(self, request, pk=None, *args, **kwargs):
        """
        GET /api/v2/datasets/{pk}/attribute_stats/
        GET /api/v2/datasets/{pk}/attribute_stats/?attribute=FIELD_NAME

        Returns min, max, mean, median, stddev, sum, count, unique_values and a
        histogram (for numeric attributes) sourced from the pre-computed stats
        stored on the Attribute model.
        """
        dataset = self.get_object()  # enforces dataset-level permissions

        attr_name = request.query_params.get("attribute")
        qs = dataset.attribute_set.all()

        if attr_name:
            try:
                attr = qs.get(attribute=attr_name)
            except Attribute.DoesNotExist:
                raise NotFound(detail=f"Attribute '{attr_name}' not found on this dataset.")

            # Auto-compute once on demand when ingest left stats empty.
            if not _has_any_stats(attr) or _needs_attribute_stats_refresh(attr):
                try:
                    attr = _backfill_attribute_stats(dataset, attr)
                except Exception:
                    logger.exception(
                        "On-demand attribute stats backfill failed",
                        extra={"dataset_pk": dataset.pk, "attribute": attr.attribute},
                    )
            response_data = _build_attribute_stats(attr)
            try:
                store_type = _get_store_type(dataset.subtype)
                live_stats = get_attribute_statistics(
                    dataset.alternate or dataset.typename,
                    attr.attribute,
                    store_type=store_type,
                    field_type=response_data.get("attribute_type") or attr.attribute_type,
                ) or {}
                if live_stats.get("inferred_field_type"):
                    response_data["attribute_type"] = live_stats["inferred_field_type"]
                if live_stats.get("total_unique") is not None:
                    response_data["total_unique"] = live_stats["total_unique"]
                if live_stats.get("groups") is not None:
                    response_data["groups"] = live_stats["groups"]
            except Exception:
                logger.exception(
                    "Live attribute stats enrichment failed",
                    extra={"dataset_pk": dataset.pk, "attribute": attr.attribute},
                )
            return Response(response_data)

        # Return stats for all attributes
        serialized = []
        for a in qs.order_by("display_order", "attribute"):
            if _needs_attribute_stats_refresh(a):
                try:
                    a = _backfill_attribute_stats(dataset, a)
                except Exception:
                    logger.exception(
                        "Bulk attribute stats refresh failed",
                        extra={"dataset_pk": dataset.pk, "attribute": a.attribute},
                    )
            serialized.append(_build_attribute_stats(a))
        return Response(serialized)
