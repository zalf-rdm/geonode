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

logger = logging.getLogger(__name__)


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
        ]
    )


def _backfill_attribute_stats(dataset, attr):
    """Compute and persist missing stats on demand for a single attribute."""
    store_type = _get_store_type(dataset.subtype)
    if not is_dataset_attribute_aggregable(store_type, attr.attribute, attr.attribute_type):
        return attr

    result = get_attribute_statistics(
        dataset.alternate or dataset.typename,
        attr.attribute,
        store_type=store_type,
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


def _build_attribute_stats(attr):
    """Build a structured stats dict from an Attribute model instance."""
    is_numeric = _parse_stat(attr.min) is not None or _parse_stat(attr.max) is not None

    # Parse unique_values into a sorted list (stored as comma-separated string)
    unique_vals = None
    if attr.unique_values and attr.unique_values not in ("NA", ""):
        raw = [v.strip() for v in attr.unique_values.split(",") if v.strip()]
        if is_numeric:
            parsed = []
            for v in raw:
                try:
                    parsed.append(float(v))
                except ValueError:
                    pass
            unique_vals = sorted(parsed) if parsed else None
        else:
            unique_vals = sorted(set(raw))[:50]  # cap at 50 for strings

    # Build histogram bins from unique numeric values if available
    histogram = None
    histogram_estimated = False
    if is_numeric and unique_vals and len(unique_vals) >= 2:
        mn = _parse_stat(attr.min)
        mx = _parse_stat(attr.max)
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
        mn = _parse_stat(attr.min)
        mx = _parse_stat(attr.max)
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
        "attribute_type": attr.attribute_type,
        "attribute_unit": attr.attribute_unit,
        "count": attr.count,
        "min": _parse_stat(attr.min),
        "max": _parse_stat(attr.max),
        "mean": _parse_stat(attr.average),
        "median": _parse_stat(attr.median),
        "stddev": _parse_stat(attr.stddev),
        "sum": _parse_stat(attr.sum),
        "unique_values": unique_vals,
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
            if not _has_any_stats(attr):
                try:
                    attr = _backfill_attribute_stats(dataset, attr)
                except Exception:
                    logger.exception(
                        "On-demand attribute stats backfill failed",
                        extra={"dataset_pk": dataset.pk, "attribute": attr.attribute},
                    )
            return Response(_build_attribute_stats(attr))

        # Return stats for all attributes
        return Response([_build_attribute_stats(a) for a in qs.order_by("display_order", "attribute")])
