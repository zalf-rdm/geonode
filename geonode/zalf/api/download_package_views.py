from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from geonode.assets.local import RawLocalAssetDownloadHandler
from geonode.assets.models import LocalAsset
from geonode.base.utils import increment_download_count
from geonode.maps.models import Map
from geonode.utils import build_absolute_uri
from geonode.zalf.api.views import allowed_authentication_classes
from geonode.zalf.download_packages import is_enabled, request_build
from geonode.zalf.models import DownloadPackage, S3Asset
from geonode.zalf.s3_assets import S3AssetDownloadHandler


def _can_manage(user):
    return user.is_authenticated and (user.is_superuser or user.can_publish_data_collection())


def _visible_map(request, mapid):
    map_obj = get_object_or_404(Map, id=mapid)
    # 404 rather than 403, so a map the caller may not see is indistinguishable
    # from one that does not exist (as in sync_metadata_view).
    if not request.user.has_perm("base.view_resourcebase", map_obj.get_self_resource()):
        raise Http404("Map does not exist")
    return map_obj


def _payload(package, include_internal):
    # "enabled" is how the client learns the feature is switched off: it then
    # hides the publish-dialog checkbox and the build button.
    enabled = is_enabled()
    if package is None:
        return {
            "enabled": enabled,
            "state": None,
            "asset_id": None,
            "download_url": None,
            "size": None,
            "built_at": None,
        }
    ready = package.is_ready
    data = {
        "enabled": enabled,
        "state": package.state,
        # The previous package keeps being served while a rebuild runs.
        "asset_id": package.asset_id,
        "download_url": (
            build_absolute_uri(reverse("download_package_file", args=(package.map_id,))) if package.asset_id else None
        ),
        "size": package.size if package.asset_id else None,
        "sha256": package.sha256 if package.asset_id else None,
        "built_at": package.built_at,
        "ready": ready,
    }
    if include_internal:
        data.update(
            {
                "error": package.error,
                "task_id": package.task_id,
                "requested_by": package.requested_by.username if package.requested_by else None,
                "updated_at": package.updated_at,
            }
        )
    return data


@api_view(["GET", "POST"])
@authentication_classes(allowed_authentication_classes)
@permission_classes([AllowAny])
def download_package_view(request, mapid):
    """
    GET  /api/v2/maps/<mapid>/download_package/
         The map's download package: state, and the asset download URL once one exists.
         `enabled: false` and an empty state while the feature is switched off
         (ZALF_DOWNLOAD_PACKAGE_ENABLED), which is how the client hides its buttons.
    POST /api/v2/maps/<mapid>/download_package/
         Queues a (re)build. Data stewards (can_publish_data_collection) and
         superusers only, and only for a published map: the package holds what the
         publication made public. 202 with `started: false` while a build is running,
         409 while the feature is switched off.
    """
    map_obj = _visible_map(request, mapid)
    if not is_enabled():
        if request.method == "GET":
            # No state either, so a package built before the switch was flipped
            # is not offered while the download endpoint answers 404.
            return Response(_payload(None, include_internal=False))
        return Response(
            {"detail": "Download packages are switched off (ZALF_DOWNLOAD_PACKAGE_ENABLED)."},
            status=status.HTTP_409_CONFLICT,
        )
    manager = _can_manage(request.user)
    if request.method == "GET":
        package = DownloadPackage.objects.filter(map=map_obj).select_related("requested_by").first()
        return Response(_payload(package, include_internal=manager))

    if not manager:
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
    if not map_obj.is_published:
        return Response(
            {"detail": "Only a published data collection has a download package."},
            status=status.HTTP_409_CONFLICT,
        )
    package, started = request_build(map_obj, user=request.user)
    return Response({**_payload(package, include_internal=True), "started": started}, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@authentication_classes(allowed_authentication_classes)
@permission_classes([AllowAny])
def download_package_file_view(request, mapid):
    """
    GET /api/v2/maps/<mapid>/download_package/download/

    The package itself: a redirect to the S3 object, or the local file.

    Authorized by *view* permission on the map, not by GeoNode's asset endpoint:
    that one requires download_resourcebase on the linked resource, and the
    publication workflow grants maps view only (`_build_public_perm_spec`). That
    is safe because the package is built from the files anonymous users may
    already download, and nothing else (`download_packages.package_resources`).

    404 while the feature is switched off (ZALF_DOWNLOAD_PACKAGE_ENABLED), even
    for a package built before: the switch takes the whole feature out of use.
    """
    map_obj = _visible_map(request, mapid)
    if not is_enabled():
        raise Http404("Download packages are switched off")
    package = DownloadPackage.objects.filter(map=map_obj).select_related("asset").first()
    if package is None or package.asset_id is None:
        raise Http404("No download package")
    asset = package.asset.get_real_instance()
    increment_download_count(map_obj.id, request.user)
    if isinstance(asset, S3Asset):
        return S3AssetDownloadHandler().create_response(asset, attachment=True)
    if isinstance(asset, LocalAsset):
        return RawLocalAssetDownloadHandler().create_response(asset, attachment=True)
    raise Http404("No download package")
