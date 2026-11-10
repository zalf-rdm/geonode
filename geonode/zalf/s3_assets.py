"""
Asset handler for objects in S3-compatible storage (zalf-rdm/geonode#659).

GeoNode ships only LocalAssetHandler, whose storage is hard-wired to the local
filesystem. This handler keeps an asset's single file in a bucket and serves it
with a redirect, so the bytes go from object storage straight to the browser.

It is provider-neutral and configured only through the dedicated
ZALF_DOWNLOAD_S3_* settings, never the global AWS_* ones, so it cannot interfere
with GeoNode's other storage. Hetzner Object Storage is the first target:
endpoint https://<location>.your-objectstorage.com, region = location.
"""

import logging
import uuid
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse

from geonode.assets.handlers import AssetDownloadHandlerInterface, AssetHandlerInterface
from geonode.utils import build_absolute_uri
from geonode.zalf.models import S3Asset

logger = logging.getLogger(__name__)


def s3_configured():
    return bool(getattr(settings, "ZALF_DOWNLOAD_S3_BUCKET", ""))


# Timeouts for validation (download_package_checks): a check must come back with
# an answer. The defaults are 60 s with 5 retries, which would hang an admin page
# for minutes on a wrong endpoint. Uploads keep the generous defaults.
CHECK_CONNECT_TIMEOUT = 5
CHECK_READ_TIMEOUT = 15


def s3_client(for_check=False):
    """
    The configured client. `for_check` trades patience for a prompt answer, so a
    misconfigured or unreachable endpoint fails in seconds instead of minutes.
    """
    import boto3
    from botocore.config import Config

    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": settings.ZALF_DOWNLOAD_S3_ADDRESSING_STYLE},
        # Since boto3 1.36 the client sends CRC checksums on every upload by default,
        # which S3-compatible providers have rejected; only send them when required.
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        **(
            {
                "connect_timeout": CHECK_CONNECT_TIMEOUT,
                "read_timeout": CHECK_READ_TIMEOUT,
                "retries": {"max_attempts": 2, "mode": "standard"},
            }
            if for_check
            else {}
        ),
    )
    return boto3.client(
        "s3",
        endpoint_url=settings.ZALF_DOWNLOAD_S3_ENDPOINT_URL or None,
        region_name=settings.ZALF_DOWNLOAD_S3_REGION or None,
        aws_access_key_id=settings.ZALF_DOWNLOAD_S3_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.ZALF_DOWNLOAD_S3_SECRET_ACCESS_KEY or None,
        config=config,
    )


def _transfer_config():
    from boto3.s3.transfer import TransferConfig

    # Managed multipart transfer; 64 MiB parts keep a 50 GB package far below the
    # 10,000-part limit of the S3 API.
    return TransferConfig(multipart_threshold=64 * 1024 * 1024, multipart_chunksize=64 * 1024 * 1024)


def object_key(filename):
    """A fresh key per upload, so a rebuild never overwrites the object still being served."""
    prefix = settings.ZALF_DOWNLOAD_S3_PREFIX.strip("/")
    return f"{prefix}/{uuid.uuid4().hex}/{filename}" if prefix else f"{uuid.uuid4().hex}/{filename}"


class S3AssetDownloadHandler(AssetDownloadHandlerInterface):
    """
    Redirects to the object. The caller (AssetViewSet._get_file) has already run
    GeoNode's permission check, so a presigned URL only reaches permitted users.
    """

    def create_response(self, asset, attachment=False, basename=None, path=None) -> HttpResponse:
        asset = asset.get_real_instance()
        if not isinstance(asset, S3Asset):
            raise TypeError("Only S3 assets are allowed")
        return HttpResponseRedirect(self.object_url(asset))

    @staticmethod
    def object_url(asset):
        client = s3_client()
        if settings.ZALF_DOWNLOAD_S3_PUBLIC:
            # A public object needs no signature; the bucket policy grants anonymous GET.
            return f"{client.meta.endpoint_url.rstrip('/')}/{asset.bucket}/{quote(asset.key)}"
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": asset.bucket, "Key": asset.key},
            ExpiresIn=settings.ZALF_DOWNLOAD_S3_URL_EXPIRY,
        )


class S3AssetHandler(AssetHandlerInterface):
    @staticmethod
    def handled_asset_class():
        return S3Asset

    def create(self, title, description, type, owner, files=None, *args, **kwargs):
        """
        Uploads the single local file in `files`. Optional kwargs: `content_type`,
        `download_name` (the filename the browser saves), `size`, `sha256`.
        """
        if not files or len(files) != 1:
            raise ValueError("Exactly one local file expected")
        path = str(files[0])
        download_name = kwargs.get("download_name") or path.rsplit("/", 1)[-1]
        bucket = settings.ZALF_DOWNLOAD_S3_BUCKET
        key = object_key(download_name)
        extra_args = {
            "ContentType": kwargs.get("content_type") or "application/octet-stream",
            "ContentDisposition": f'attachment; filename="{download_name}"',
        }
        # No ACL: canned-ACL support varies across S3-compatible providers. Public
        # mode (ZALF_DOWNLOAD_S3_PUBLIC) relies on a bucket policy instead.
        s3_client().upload_file(path, bucket, key, ExtraArgs=extra_args, Config=_transfer_config())
        asset = S3Asset(
            title=title,
            description=description,
            type=type,
            owner=owner,
            bucket=bucket,
            key=key,
            size=kwargs.get("size"),
            sha256=kwargs.get("sha256") or "",
        )
        asset.save()
        return asset

    def remove_data(self, asset, **kwargs):
        asset = asset.get_real_instance()
        try:
            s3_client().delete_object(Bucket=asset.bucket, Key=asset.key)
        except Exception:
            # The row is already gone; an orphaned object is preferable to a failed delete.
            logger.exception(f"Could not delete S3 object {asset.bucket}/{asset.key}")

    def replace_data(self, asset, files: list):
        raise NotImplementedError("S3 assets are replaced by creating a new asset")

    def clone(self, source):
        """Server-side copy to a new key; used when GeoNode clones the map the asset belongs to."""
        source = source.get_real_instance()
        key = object_key(source.key.rsplit("/", 1)[-1])
        s3_client().copy({"Bucket": source.bucket, "Key": source.key}, source.bucket, key, Config=_transfer_config())
        clone = S3Asset(
            title=source.title,
            description=source.description,
            type=source.type,
            owner=source.owner,
            bucket=source.bucket,
            key=key,
            size=source.size,
            sha256=source.sha256,
        )
        clone.save()
        return clone

    def create_download_url(self, asset) -> str:
        return build_absolute_uri(reverse("assets-download", args=(asset.pk,)))

    def create_link_url(self, asset) -> str:
        return build_absolute_uri(reverse("assets-link", args=(asset.pk,)))

    def get_download_handler(self, asset=None):
        return S3AssetDownloadHandler()

    def get_storage_manager(self, asset=None):
        return None
