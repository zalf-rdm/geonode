"""
Validation for download packages (zalf-rdm/geonode#659).

A `DownloadPackage` row records what the last build *concluded*. It cannot say
whether the stored object is still there: a bucket lifecycle rule, a manual
`s3cmd del`, a failed `remove_data` (which logs and swallows, so an orphan is
preferable to a failed delete) or a restored database all leave the row saying
`ready` while the download is 404 or, worse, truncated.

This module asks the storage itself. It is the single implementation behind
both front ends -- `manage.py download_package_status` and the *Validate
storage* page in the Download packages admin -- so the two can never disagree.

Checks are read-only: nothing here builds, deletes or rewrites anything.
"""

import datetime
import hashlib
import logging
import os
import zipfile

from django.conf import settings

from geonode.maps.models import Map
from geonode.zalf.download_packages import CHUNK, PACKAGE_ASSET_TYPE
from geonode.zalf.models import DownloadPackage, S3Asset

logger = logging.getLogger(__name__)

# Statuses, worst last. `rank()` orders a report by how much attention a row needs.
OK = "ok"
# --db-only: the build recorded a package and nothing asked the storage. Kept
# distinct from OK, which asserts the object is really there.
READY = "ready"
PENDING = "pending"
MISSING = "missing"
STALE = "stale"
FAILED = "failed"
NO_ASSET = "no-asset"
MISMATCH = "mismatch"
CORRUPT = "corrupt"
GONE = "gone"
UNREACHABLE = "unreachable"

SEVERITY = [OK, READY, PENDING, MISSING, STALE, FAILED, NO_ASSET, MISMATCH, CORRUPT, GONE, UNREACHABLE]

# What `--fail-on-broken` and the admin page's warning count react to.
#
# UNREACHABLE is in here on purpose: "the storage could not be asked" is not
# proof of damage, but it means downloads are failing for visitors too, which is
# worth the same alert. PENDING and MISSING are not faults -- a build is on its
# way, or none was ever requested (`build_download_packages --missing-only`).
BROKEN = frozenset({STALE, FAILED, NO_ASSET, MISMATCH, CORRUPT, GONE, UNREACHABLE})

# Default ceiling for `--deep`: above it the object is not downloaded and the
# checksum is left unverified, so one huge package cannot stall a nightly check.
DEFAULT_MAX_DEEP_BYTES = 2 * 1024**3


def rank(status):
    return SEVERITY.index(status) if status in SEVERITY else len(SEVERITY)


class CheckResult:
    """One row of a validation report."""

    def __init__(self, map_id, map_title, status, detail="", location="", stored_size=None, package=None):
        self.map_id = map_id
        self.map_title = map_title
        self.status = status
        self.detail = detail
        self.location = location
        # Size as the storage reports it, which is the point of the exercise:
        # package.size is what the build believed it had written.
        self.stored_size = stored_size
        self.package = package
        self.built_at = package.built_at if package else None

    @property
    def is_broken(self):
        return self.status in BROKEN

    @property
    def is_ok(self):
        return self.status == OK

    def __repr__(self):
        return f"<CheckResult map={self.map_id} {self.status}>"


def _is_stale(package):
    """A pending/building row whose worker cannot still be alive (past the task time limit)."""
    stale_after = datetime.timedelta(seconds=settings.ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT)
    return package.updated_at <= datetime.datetime.now(datetime.timezone.utc) - stale_after


def _last_error_line(package):
    return package.error.strip().splitlines()[-1] if package.error.strip() else "no error recorded"


def _check_zip_and_checksum(path, package):
    """(status, detail) for a readable local copy of the package."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            # testzip() CRCs every member, which is what catches a truncated
            # upload that still carries a valid central directory.
            broken_member = archive.testzip()
    except zipfile.BadZipFile as error:
        return CORRUPT, f"not a readable ZIP: {error}"
    if broken_member:
        return CORRUPT, f"ZIP member fails its CRC: {broken_member}"
    if not names:
        return CORRUPT, "the ZIP holds no members"

    if package.sha256:
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(CHUNK), b""):
                digest.update(chunk)
        if digest.hexdigest() != package.sha256:
            return MISMATCH, f"sha256 is {digest.hexdigest()[:12]}…, the build recorded {package.sha256[:12]}…"
        return OK, "ZIP readable, sha256 matches the build"
    return OK, "ZIP readable (the build recorded no sha256 to compare)"


def _check_s3_asset(package, asset, deep, max_deep_bytes):
    import tempfile

    from botocore.exceptions import BotoCoreError, ClientError

    from geonode.zalf.s3_assets import s3_client

    location = f"s3://{asset.bucket}/{asset.key}"
    row = dict(map_id=package.map_id, map_title=package.map.title, location=location, package=package)

    try:
        client = s3_client(for_check=True)
        head = client.head_object(Bucket=asset.bucket, Key=asset.key)
    except ClientError as error:
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound"):
            return CheckResult(**row, status=GONE, detail="the object is not in the bucket")
        if code in ("403", "AccessDenied"):
            # Distinguishable from a missing object only on a bucket that allows
            # ListBucket; on one that does not, S3 answers 403 for both.
            return CheckResult(**row, status=UNREACHABLE, detail=f"access denied ({code}); check the credentials")
        return CheckResult(**row, status=UNREACHABLE, detail=f"{code or 'ClientError'}: {error}")
    except BotoCoreError as error:
        return CheckResult(**row, status=UNREACHABLE, detail=f"{type(error).__name__}: {error}")

    stored = head.get("ContentLength")
    row["stored_size"] = stored
    if package.size and stored != package.size:
        return CheckResult(
            **row, status=MISMATCH, detail=f"the bucket holds {stored} bytes, the build recorded {package.size}"
        )
    if not stored:
        return CheckResult(**row, status=MISMATCH, detail="the object is empty")

    notes = []
    if head.get("ContentType") != "application/zip":
        # Not a fault: the bytes are fine, but the browser will not treat it as a ZIP.
        notes.append(f"content-type is {head.get('ContentType') or 'unset'}, not application/zip")
    if "attachment" not in (head.get("ContentDisposition") or ""):
        notes.append("no attachment content-disposition, so the browser will not save it under its name")

    if deep:
        if stored > max_deep_bytes:
            notes.append(f"deep check skipped: {stored} bytes is over the {max_deep_bytes}-byte limit")
        else:
            with tempfile.TemporaryDirectory(prefix="pkg-check-") as tmp:
                path = os.path.join(tmp, "package.zip")
                try:
                    client.download_file(asset.bucket, asset.key, path)
                except (ClientError, BotoCoreError) as error:
                    return CheckResult(**row, status=UNREACHABLE, detail=f"could not download it: {error}")
                status, detail = _check_zip_and_checksum(path, package)
            if status != OK:
                return CheckResult(**row, status=status, detail=detail)
            notes.append(detail)

    return CheckResult(**row, status=OK, detail="; ".join(notes))


def _local_path(asset):
    paths = [str(p) for p in (getattr(asset, "location", None) or [])]
    return paths[0] if paths else ""


def _check_local_asset(package, asset, deep, max_deep_bytes):
    paths = [str(p) for p in (asset.location or [])]
    row = dict(map_id=package.map_id, map_title=package.map.title, location=paths[0] if paths else "", package=package)
    if not paths:
        return CheckResult(**row, status=NO_ASSET, detail="the asset records no file location")

    present = [p for p in paths if os.path.isfile(p)]
    if not present:
        return CheckResult(**row, status=GONE, detail=f"the file is not on disk ({len(paths)} path(s) recorded)")

    path = present[0]
    stored = os.path.getsize(path)
    row["stored_size"] = stored
    if package.size and stored != package.size:
        return CheckResult(
            **row, status=MISMATCH, detail=f"the file is {stored} bytes, the build recorded {package.size}"
        )
    if not stored:
        return CheckResult(**row, status=MISMATCH, detail="the file is empty")

    if deep:
        if stored > max_deep_bytes:
            detail = f"deep check skipped: {stored} bytes is over the {max_deep_bytes}-byte limit"
        else:
            status, detail = _check_zip_and_checksum(path, package)
            if status != OK:
                return CheckResult(**row, status=status, detail=detail)
        return CheckResult(**row, status=OK, detail=detail)

    return CheckResult(**row, status=OK, detail="")


def check_package(package, deep=False, max_deep_bytes=DEFAULT_MAX_DEEP_BYTES, storage=True):
    """
    Validates one package against its storage. Never raises: a storage that
    cannot be reached is reported as UNREACHABLE, since a check that explodes
    tells an operator less than one that says why.

    With `storage=False` nothing is asked of the bucket or the disk and a
    package the build recorded comes back as READY rather than OK -- the cheap
    listing, for when the storage is slow, unreachable or simply not the
    question. The faults that live in the row itself (pending, stale, failed,
    no-asset) are reported either way.
    """
    row = dict(map_id=package.map_id, map_title=package.map.title, package=package)

    if package.state in (DownloadPackage.STATE_PENDING, DownloadPackage.STATE_BUILDING):
        if _is_stale(package):
            return CheckResult(
                **row,
                status=STALE,
                detail=(
                    f"still {package.state} since {package.updated_at:%Y-%m-%d %H:%M}, past the "
                    f"{settings.ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT}s task time limit: the worker died. "
                    "A rebuild may be requested."
                ),
            )
        return CheckResult(**row, status=PENDING, detail=f"a build is {package.state}")

    if package.state == DownloadPackage.STATE_FAILED:
        return CheckResult(**row, status=FAILED, detail=_last_error_line(package))

    if package.asset_id is None:
        return CheckResult(
            **row, status=NO_ASSET, detail="state is ready but no asset is linked: the asset was deleted under it"
        )

    try:
        asset = package.asset.get_real_instance()
    except Exception as error:  # pragma: no cover - a broken polymorphic row
        return CheckResult(**row, status=NO_ASSET, detail=f"the asset row cannot be resolved: {error}")

    if not storage:
        # bucket and key are columns, so the location costs nothing to report.
        location = f"s3://{asset.bucket}/{asset.key}" if isinstance(asset, S3Asset) else _local_path(asset)
        return CheckResult(
            **row,
            status=READY,
            detail="the build recorded it; the storage was not asked",
            location=location,
            stored_size=package.size,
        )

    try:
        if isinstance(asset, S3Asset):
            return _check_s3_asset(package, asset, deep, max_deep_bytes)
        return _check_local_asset(package, asset, deep, max_deep_bytes)
    except Exception as error:
        logger.exception(f"Validating the download package of map {package.map_id} failed")
        return CheckResult(**row, status=UNREACHABLE, detail=f"{type(error).__name__}: {error}")


def check_packages(packages=None, map_ids=None, include_missing=False, deep=False, max_deep_bytes=None, storage=True):
    """
    Validates many packages and returns the report, worst rows first.

    `include_missing` adds a MISSING row for every published map that has no
    package at all, which is what makes the report a complete answer to "which
    collections offer a download" rather than only "are the rows we have sound".
    """
    max_deep_bytes = DEFAULT_MAX_DEEP_BYTES if max_deep_bytes is None else max_deep_bytes
    if packages is None:
        packages = DownloadPackage.objects.all()
    packages = packages.select_related("map", "asset")
    if map_ids:
        packages = packages.filter(map_id__in=map_ids)

    results = [
        check_package(package, deep=deep, max_deep_bytes=max_deep_bytes, storage=storage) for package in packages
    ]

    if include_missing:
        have = {result.map_id for result in results}
        maps = Map.objects.filter(is_published=True).exclude(pk__in=have)
        if map_ids:
            maps = maps.filter(pk__in=map_ids)
        for map_obj in maps:
            results.append(
                CheckResult(
                    map_id=map_obj.pk,
                    map_title=map_obj.title,
                    status=MISSING,
                    detail="published, but no package was ever built",
                )
            )

    results.sort(key=lambda result: (-rank(result.status), result.map_id))
    return results


def summarize(results):
    """{status: count} in severity order, for a one-line summary."""
    counts = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return {status: counts[status] for status in SEVERITY if status in counts}


def find_orphans(limit=5000):
    """
    Objects under the configured prefix that no S3Asset references.

    These are the other half of the picture: `remove_data` logs and swallows a
    failed delete, and a restored database forgets keys entirely, so the bucket
    can keep paying for objects nothing will ever serve. Returns
    (orphans, truncated) where each orphan is {key, size, last_modified}.
    """
    from botocore.exceptions import BotoCoreError, ClientError

    from geonode.zalf.s3_assets import s3_client, s3_configured

    if not s3_configured():
        return [], False

    bucket = settings.ZALF_DOWNLOAD_S3_BUCKET
    prefix = settings.ZALF_DOWNLOAD_S3_PREFIX.strip("/")
    known = set(S3Asset.objects.filter(bucket=bucket).values_list("key", flat=True))

    orphans = []
    truncated = False
    try:
        paginator = s3_client(for_check=True).get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/" if prefix else ""):
            for obj in page.get("Contents", []):
                if obj["Key"] in known or obj["Key"].endswith("/"):
                    continue
                orphans.append({"key": obj["Key"], "size": obj["Size"], "last_modified": obj["LastModified"]})
                if len(orphans) >= limit:
                    return orphans, True
    except (ClientError, BotoCoreError) as error:
        raise RuntimeError(f"Could not list {bucket}: {error}") from error
    return orphans, truncated


def find_dangling_assets():
    """
    Package assets that no DownloadPackage row points at.

    `_delete_asset` removes the previous asset on every rebuild, so a leftover
    here means a delete did not complete -- the object is still being paid for
    and nothing will ever serve it.
    """
    referenced = set(DownloadPackage.objects.exclude(asset_id=None).values_list("asset_id", flat=True))
    return list(S3Asset.objects.filter(type=PACKAGE_ASSET_TYPE).exclude(pk__in=referenced))
