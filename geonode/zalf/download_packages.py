"""
Download packages for published data collections (zalf-rdm/geonode#659).

A package is one ZIP holding every resource of a map (data collection) that
anonymous users may download: after publication that is exactly the set the
publication made public (see `_build_public_perm_spec` in api/views.py). It is
stored as an Asset linked to the map -- an S3Asset when ZALF_DOWNLOAD_S3_BUCKET
is set, otherwise GeoNode's LocalAsset -- so the asset endpoint, its permission
check and the delete cleanup all apply.

Files come from what GeoNode already keeps, in this order:
  1. the resource's own asset: the original upload of a dataset, a document's file;
  2. for datasets without one, GeoNode's export through GeoServer WPS gs:Download
     (DatasetDownloadHandler), streamed to disk.
"""

import datetime
import hashlib
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass

import requests
from django.conf import settings
from django.db import transaction
from django.template.loader import get_template
from django.utils.text import slugify

from geonode.assets.handlers import asset_handler_registry
from geonode.assets.models import LocalAsset
from geonode.assets.utils import create_asset_and_link, get_default_asset
from geonode.layers.download_handler import DatasetDownloadHandler
from geonode.security.permissions import DOWNLOAD_PERMISSIONS
from geonode.security.registry import permissions_registry
from geonode.zalf.models import DownloadPackage

logger = logging.getLogger(__name__)

PACKAGE_ASSET_TYPE = "download_package"
CHUNK = 1024 * 1024


class PackageTooLarge(Exception):
    pass


@dataclass
class ManifestEntry:
    arcname: str
    resource_id: int
    resource_title: str
    source: str  # "original" | "export"
    size: int
    sha256: str


# ---------------------------------------------------------------------------
# Contents
# ---------------------------------------------------------------------------


def _anonymous_can_download(resource):
    from guardian.utils import get_anonymous_user

    perms = permissions_registry.get_perms(instance=resource.get_self_resource(), user=get_anonymous_user())
    return set(DOWNLOAD_PERMISSIONS).issubset(perms)


def package_resources(map_obj):
    """The map's layers and linked resources that anonymous users may download, in a stable order."""
    seen = set()
    resources = []
    # Map.get_linked_resources chains real links with on-the-fly ones for the map
    # layers, so it is an iterator, not a queryset.
    for link in sorted(map_obj.get_linked_resources(), key=lambda link: link.target_id):
        resource = link.target.get_real_instance()
        if resource.pk in seen or resource.resource_type == "map":
            continue
        seen.add(resource.pk)
        if _anonymous_can_download(resource):
            resources.append(resource)
    return resources


def _local_files(resource):
    """Files of the resource's own LocalAsset (an original upload or a document), if present on disk."""
    asset = get_default_asset(resource)
    if not isinstance(asset, LocalAsset):
        return []
    return [path for path in (asset.location or []) if os.path.isfile(path)]


class ZalfDatasetExporter(DatasetDownloadHandler):
    """
    GeoNode's dataset export (WPS gs:Download), for a task instead of a request.

    Reuses the request template and the format rules of
    DatasetDownloadHandler.process_dowload, but takes the resource directly (a task
    has no request whose user permissions could be resolved) and streams the
    response to a file, where upstream reads it fully into memory.
    """

    EXTENSIONS = {
        "application/zip": "zip",
        "application/json": "json",
        "image/tiff": "tif",
        "text/csv": "csv",
        "application/geopackage+sqlite3": "gpkg",
    }

    def __init__(self, resource):
        super().__init__(request=None, resource_name=resource.alternate)
        self._resource = resource

    def get_resource(self):
        return self._resource

    def output_format(self):
        resource = self._resource
        if resource.subtype == "tabular":
            return "text/csv"
        if resource.is_vector():
            return getattr(settings, "DEFAULT_VECTOR_DOWNLOAD_FORMAT", "application/json")
        return "image/tiff"

    def export_to(self, directory, basename):
        _format = self.output_format()
        payload = get_template("geoserver/dataset_download.xml").render(
            {"alternate": self._resource.alternate, "download_format": _format}
        )
        server = settings.OGC_SERVER["default"]
        url = f"{server['LOCATION']}ows?service=WPS&version=1.0.0&REQUEST=Execute"
        with requests.post(
            url,
            data=payload.encode("utf-8"),
            headers={"Content-type": "application/xml"},
            auth=(server.get("USER"), server.get("PASSWORD")),
            stream=True,
            timeout=(30, settings.ZALF_DOWNLOAD_PACKAGE_EXPORT_TIMEOUT),
        ) as response:
            mime = (response.headers.get("Content-Type") or "").split(";")[0].strip()
            # A failed WPS execution still answers 200, with an XML ExceptionReport.
            if response.status_code != 200 or mime in ("text/xml", "application/xml"):
                raise RuntimeError(
                    f"GeoServer export of '{self._resource.alternate}' failed "
                    f"(HTTP {response.status_code}): {response.text[:500]}"
                )
            path = os.path.join(directory, f"{basename}.{self.EXTENSIONS.get(mime, 'zip')}")
            with open(path, "wb") as target:
                for chunk in response.iter_content(CHUNK):
                    target.write(chunk)
        return path


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _folder(resource):
    return f"{resource.resource_type}s/{resource.pk}-{slugify(resource.title)[:60] or 'resource'}"


def package_filename(map_obj):
    return f"{slugify(map_obj.title)[:80] or 'data-collection'}-{map_obj.pk}.zip"


def _manifest(map_obj, entries, skipped):
    lines = [
        f"Data collection: {map_obj.title}",
        f"Map ID: {map_obj.pk}",
        f"DOI: {map_obj.doi or '-'}",
        f"Built: {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}",
        "",
        "Each file, the resource it belongs to, how it was obtained (original = as deposited,",
        "export = generated by the repository) and its SHA-256 checksum:",
        "",
    ]
    for e in entries:
        lines.append(f"{e.arcname}\t{e.resource_id}\t{e.resource_title}\t{e.source}\t{e.size}\t{e.sha256}")
    if skipped:
        lines += ["", "Resources without downloadable files:"]
        lines += [f"{r.pk}\t{r.title}" for r in skipped]
    return "\n".join(lines) + "\n"


def build_package_file(map_obj, build_dir):
    """Writes the ZIP into `build_dir`; returns (path, size, sha256)."""
    max_bytes = settings.ZALF_DOWNLOAD_PACKAGE_MAX_BYTES
    exports_dir = os.path.join(build_dir, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    zip_path = os.path.join(build_dir, package_filename(map_obj))

    entries, skipped, total = [], [], 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for resource in package_resources(map_obj):
            files, source = _local_files(resource), "original"
            if not files and resource.resource_type == "dataset":
                files = [ZalfDatasetExporter(resource).export_to(exports_dir, f"{resource.pk}")]
                source = "export"
            if not files:
                skipped.append(resource)
                continue
            for path in files:
                size = os.path.getsize(path)
                total += size
                if max_bytes and total > max_bytes:
                    raise PackageTooLarge(f"Package exceeds ZALF_DOWNLOAD_PACKAGE_MAX_BYTES ({max_bytes} bytes)")
                arcname = f"{_folder(resource)}/{os.path.basename(path)}"
                archive.write(path, arcname)
                entries.append(ManifestEntry(arcname, resource.pk, resource.title, source, size, _sha256(path)))
            if source == "export":
                for path in files:
                    os.remove(path)
        if not entries:
            raise ValueError("The data collection has no publicly downloadable files")
        archive.writestr("MANIFEST.txt", _manifest(map_obj, entries, skipped))

    return zip_path, os.path.getsize(zip_path), _sha256(zip_path)


def store_package(map_obj, zip_path, size, sha256):
    """Registers the ZIP as an asset linked to the map, in S3 when configured."""
    from geonode.zalf.s3_assets import S3AssetHandler, s3_configured

    if s3_configured():
        handler = asset_handler_registry.get_handler(S3AssetHandler.handled_asset_class())
        asset = handler.create(
            title="Download package",
            description=f"All publicly downloadable data of map {map_obj.pk}",
            type=PACKAGE_ASSET_TYPE,
            owner=map_obj.owner,
            files=[zip_path],
            content_type="application/zip",
            download_name=os.path.basename(zip_path),
            size=size,
            sha256=sha256,
        )
        from geonode.assets.utils import create_link

        create_link(
            map_obj,
            asset,
            asset_handler=handler,
            link_type="data",
            extension="zip",
            name="Download package",
            mime="application/zip",
        )
        return asset

    asset, _ = create_asset_and_link(
        map_obj,
        map_obj.owner,
        [zip_path],
        title="Download package",
        description=f"All publicly downloadable data of map {map_obj.pk}",
        link_type="data",
        extension="zip",
        asset_type=PACKAGE_ASSET_TYPE,
        mime="application/zip",
        clone_files=True,
    )
    return asset


def _delete_asset(asset):
    """Removes an old package asset; its post_delete signal removes the stored file."""
    from geonode.base.models import Link

    Link.objects.filter(asset=asset).delete()
    asset.delete()


def run_build(map_id, task_id=""):
    """The task body: build, store, swap the package's asset. Raises nothing; records failures."""
    package = DownloadPackage.objects.select_related("map").get(map_id=map_id)
    package.state, package.task_id, package.error = DownloadPackage.STATE_BUILDING, task_id, ""
    package.save(update_fields=["state", "task_id", "error", "updated_at"])

    map_obj = package.map
    build_dir = os.path.join(settings.ZALF_DOWNLOAD_PACKAGE_BUILD_ROOT, f"{map_obj.pk}-{task_id or 'manual'}")
    os.makedirs(build_dir, exist_ok=True)
    try:
        zip_path, size, sha256 = build_package_file(map_obj, build_dir)
        asset = store_package(map_obj, zip_path, size, sha256)
        previous = package.asset.get_real_instance() if package.asset_id else None
        package.asset = asset
        package.state, package.size, package.sha256 = DownloadPackage.STATE_READY, size, sha256
        package.built_at = datetime.datetime.now(datetime.timezone.utc)
        package.save()
        # Only now: until the new asset is linked, the old one keeps being served.
        if previous is not None:
            _delete_asset(previous)
    except Exception as error:
        logger.exception(f"Building the download package of map {map_id} failed")
        package.state, package.error = DownloadPackage.STATE_FAILED, str(error)[:4000]
        package.save(update_fields=["state", "error", "updated_at"])
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
    return package


# ---------------------------------------------------------------------------
# Triggering
# ---------------------------------------------------------------------------


def _is_running(package):
    if package.state not in (DownloadPackage.STATE_PENDING, DownloadPackage.STATE_BUILDING):
        return False
    # A worker that died mid-build leaves the row in "building"; after the task's
    # own time limit has passed it cannot still be running.
    stale_after = datetime.timedelta(seconds=settings.ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT)
    return package.updated_at > datetime.datetime.now(datetime.timezone.utc) - stale_after


def request_build(map_obj, user=None):
    """
    Queues a (re)build of the map's package, unless one is pending or running.
    Returns (package, started). The task is sent on commit, so it sees the
    caller's writes -- after publication, the public permissions.
    """
    from geonode.zalf.tasks import build_download_package

    with transaction.atomic():
        package, created = DownloadPackage.objects.select_for_update().get_or_create(map=map_obj)
        if not created and _is_running(package):
            return package, False
        package.state, package.error, package.requested_by = DownloadPackage.STATE_PENDING, "", user
        package.save(update_fields=["state", "error", "requested_by", "updated_at"])
    transaction.on_commit(lambda: build_download_package.apply_async(args=[map_obj.pk]))
    return package, True
