"""
Tests for map download packages (zalf-rdm/geonode#659).

The packages are built and stored as LocalAssets here (no S3 bucket configured);
the S3 handler is tested on its own against a mocked boto3 client, since moto is
not a dependency and real providers (Hetzner) are smoke-tested by hand.
"""

import base64
import hashlib
import io
import os
import shutil
import tempfile
import zipfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from geonode.assets.utils import create_asset_and_link, get_default_asset
from geonode.base.models import LinkedResource, ResourceBase
from geonode.base.populate_test_data import create_single_dataset, create_single_doc
from geonode.maps.models import Map, MapLayer
from geonode.zalf import download_packages
from geonode.zalf.api.serializer import PublishSerializer
from geonode.zalf.api.views import _build_public_perm_spec
from geonode.zalf.models import DownloadPackage, S3Asset
from geonode.zalf.s3_assets import S3AssetDownloadHandler, S3AssetHandler

User = get_user_model()

ENV = {
    "RESOURCE_PUBLISHING": False,
    "ADMIN_MODERATE_UPLOADS": False,
    # Nothing is public unless a test publishes it, as the workflow does.
    "DEFAULT_ANONYMOUS_VIEW_PERMISSION": False,
    "DEFAULT_ANONYMOUS_DOWNLOAD_PERMISSION": False,
    "KEYCLOAK_SSO_ENABLED": False,
    "ZALF_DOWNLOAD_S3_BUCKET": "",
}


def basic_auth(username, password="pw"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"HTTP_AUTHORIZATION": f"Basic {token}"}


def publish(resource):
    """What the publication workflow does to a resource's permissions."""
    ResourceBase.objects.filter(pk=resource.pk).update(is_published=True, is_approved=True)
    resource.refresh_from_db()
    resource.set_permissions(_build_public_perm_spec(resource))


class PackageTestBase(TestCase):
    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.build_root = os.path.join(self.tmp, "builds")
        self.settings_override = override_settings(**ENV, ZALF_DOWNLOAD_PACKAGE_BUILD_ROOT=self.build_root)
        self.settings_override.enable()
        self.owner = User.objects.create_user("pkg-owner", "o@example.test", "pw")
        self.admin = User.objects.create_superuser("pkg-admin", "a@example.test", "pw")
        self.map = Map.objects.create(owner=self.owner, title="Soil Collection")
        self.map.set_default_permissions()

    def tearDown(self):
        for package in DownloadPackage.objects.select_related("asset"):
            if package.asset_id:
                package.asset.get_real_instance().delete()
        self.settings_override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def file(self, name, content=b"data"):
        directory = tempfile.mkdtemp(dir=self.tmp)
        path = os.path.join(directory, name)
        with open(path, "wb") as target:
            target.write(content)
        return path

    def dataset(self, name, files=None):
        dataset = create_single_dataset(name, owner=self.owner)
        MapLayer.objects.create(map=self.map, dataset=dataset, name=dataset.alternate)
        if files:
            create_asset_and_link(dataset, self.owner, files, title="Original", clone_files=False)
        return dataset

    def document(self, name):
        # create_single_doc stores the document's file as its asset, as an upload does.
        document = create_single_doc(name, owner=self.owner)
        LinkedResource.objects.create(source=self.map, target=document)
        return document

    def build(self):
        DownloadPackage.objects.get_or_create(map=self.map)
        return download_packages.run_build(self.map.pk, task_id="test")

    def archive(self, package):
        asset = package.asset.get_real_instance()
        return zipfile.ZipFile(asset.location[0])


class TestPackageContents(PackageTestBase):
    def test_packages_the_original_files_of_published_resources_only(self):
        shp = self.file("soil.shp", b"shape")
        public_dataset = self.dataset("public_ds", [shp, self.file("soil.dbf", b"table")])
        private_dataset = self.dataset("private_ds", [self.file("secret.shp")])
        document = self.document("report")
        document_file = os.path.basename(get_default_asset(document).location[0])
        for resource in (self.map, public_dataset, document):
            publish(resource)

        package = self.build()

        self.assertEqual(package.state, DownloadPackage.STATE_READY, package.error)
        names = self.archive(package).namelist()
        self.assertIn(f"datasets/{public_dataset.pk}-public_ds/soil.shp", names)
        self.assertIn(f"datasets/{public_dataset.pk}-public_ds/soil.dbf", names)
        self.assertIn(f"documents/{document.pk}-report/{document_file}", names)
        self.assertIn("MANIFEST.txt", names)
        self.assertFalse(any(str(private_dataset.pk) + "-" in name for name in names))

    def test_manifest_lists_checksums_and_the_package_is_linked_to_the_map(self):
        dataset = self.dataset("ds", [self.file("a.csv", b"x,y\n1,2\n")])
        publish(self.map)
        publish(dataset)

        package = self.build()

        manifest = self.archive(package).read("MANIFEST.txt").decode()
        self.assertIn("original", manifest)
        self.assertIn(hashlib.sha256(b"x,y\n1,2\n").hexdigest(), manifest)
        self.assertTrue(self.map.link_set.filter(asset=package.asset, link_type="data").exists())
        self.assertEqual(package.size, os.path.getsize(package.asset.get_real_instance().location[0]))

    def test_datasets_without_an_original_are_exported_through_geoserver(self):
        dataset = self.dataset("no_original")
        publish(self.map)
        publish(dataset)
        response = mock.MagicMock(status_code=200, headers={"Content-Type": "application/zip"})
        response.iter_content.return_value = [b"PK-export"]
        response.__enter__.return_value = response

        with mock.patch.object(download_packages.requests, "post", return_value=response) as post:
            package = self.build()

        self.assertEqual(package.state, DownloadPackage.STATE_READY, package.error)
        self.assertIn("gs:Download", post.call_args.kwargs["data"].decode())
        archive = self.archive(package)
        self.assertEqual(archive.read(f"datasets/{dataset.pk}-no_original/{dataset.pk}.zip"), b"PK-export")
        self.assertIn("export", archive.read("MANIFEST.txt").decode())

    def test_a_geoserver_exception_report_fails_the_build(self):
        dataset = self.dataset("broken")
        publish(self.map)
        publish(dataset)
        response = mock.MagicMock(status_code=200, headers={"Content-Type": "text/xml"}, text="<ExceptionReport/>")
        response.__enter__.return_value = response

        with mock.patch.object(download_packages.requests, "post", return_value=response):
            package = self.build()

        self.assertEqual(package.state, DownloadPackage.STATE_FAILED)
        self.assertIn("ExceptionReport", package.error)
        self.assertIsNone(package.asset_id)

    def test_nothing_public_fails_instead_of_storing_an_empty_package(self):
        self.dataset("unpublished", [self.file("x.shp")])
        publish(self.map)

        package = self.build()

        self.assertEqual(package.state, DownloadPackage.STATE_FAILED)
        self.assertIsNone(package.asset_id)

    def test_size_limit(self):
        dataset = self.dataset("big", [self.file("big.bin", b"0" * 2048)])
        publish(self.map)
        publish(dataset)

        with override_settings(ZALF_DOWNLOAD_PACKAGE_MAX_BYTES=1024):
            package = self.build()

        self.assertEqual(package.state, DownloadPackage.STATE_FAILED)
        self.assertIn("ZALF_DOWNLOAD_PACKAGE_MAX_BYTES", package.error)

    def test_rebuild_replaces_the_previous_asset_and_removes_its_file(self):
        dataset = self.dataset("ds", [self.file("a.shp")])
        publish(self.map)
        publish(dataset)
        first = self.build().asset.get_real_instance()
        first_file = first.location[0]

        second = self.build()

        self.assertNotEqual(second.asset_id, first.pk)
        self.assertFalse(S3Asset.objects.filter(pk=first.pk).exists())
        self.assertFalse(type(first).objects.filter(pk=first.pk).exists())
        self.assertFalse(os.path.exists(first_file))
        self.assertFalse(os.listdir(self.build_root))


class TestTriggers(PackageTestBase):
    def test_request_build_queues_once_on_commit(self):
        with mock.patch("geonode.zalf.tasks.build_download_package.apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                package, started = download_packages.request_build(self.map, user=self.admin)
            again, started_again = download_packages.request_build(self.map, user=self.admin)

        self.assertTrue(started)
        self.assertFalse(started_again)
        self.assertEqual(package.pk, again.pk)
        self.assertEqual(package.state, DownloadPackage.STATE_PENDING)
        apply_async.assert_called_once_with(args=[self.map.pk])

    def test_a_stale_build_can_be_restarted(self):
        DownloadPackage.objects.create(map=self.map, state=DownloadPackage.STATE_BUILDING)
        with (
            override_settings(ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT=0),
            mock.patch("geonode.zalf.tasks.build_download_package.apply_async"),
        ):
            _, started = download_packages.request_build(self.map)
        self.assertTrue(started)

    def test_publish_serializer_builds_by_default(self):
        data = {"owner": 1, "resources": [1], "doi_prefix": "10.1234"}
        self.assertTrue(PublishSerializer(data=data).is_valid())
        serializer = PublishSerializer(data=data)
        serializer.is_valid()
        self.assertTrue(serializer.validated_data["build_download_package"])
        serializer = PublishSerializer(data={**data, "build_download_package": False})
        serializer.is_valid()
        self.assertFalse(serializer.validated_data["build_download_package"])

    def _publish(self, build):
        from geonode.zalf.api import views

        dataset = self.dataset("pub", [self.file("a.shp")])
        ResourceBase.objects.filter(pk=dataset.pk).update(is_approved=True)
        dataset.refresh_from_db()
        payload = {"owner": self.owner.pk, "resources": [dataset.pk], "doi_prefix": "10.1234"}
        if build is not None:
            payload["build_download_package"] = build
        serializer = PublishSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        with (
            mock.patch.object(views, "validate_doi_prefix"),
            mock.patch.object(views, "get_datacite_account_for_prefix"),
            mock.patch.object(views, "register_doi", return_value="10.1234/x"),
            mock.patch.object(download_packages, "request_build") as request_build,
        ):
            views._publish_data_collection(self.map, serializer.validated_data, user=self.admin)
        return request_build

    def test_publication_queues_the_build_by_default(self):
        self._publish(build=None).assert_called_once_with(self.map, user=self.admin)

    def test_publication_can_skip_the_build(self):
        self._publish(build=False).assert_not_called()


class TestDownloadPackageApi(PackageTestBase):
    def url(self, suffix=""):
        return f"/api/v2/maps/{self.map.pk}/download_package/{suffix}"

    def test_get_before_any_build(self):
        publish(self.map)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["state"])

    def test_invisible_map_is_404(self):
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_post_requires_a_data_steward(self):
        publish(self.map)
        User.objects.create_user("visitor", "v@example.test", "pw")
        self.assertEqual(self.client.post(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), **basic_auth("visitor")).status_code, 403)

    def test_post_requires_a_published_map(self):
        # Without RESOURCE_PUBLISHING a new map is published on save.
        ResourceBase.objects.filter(pk=self.map.pk).update(is_published=False)
        response = self.client.post(self.url(), **basic_auth("pkg-admin"))
        self.assertEqual(response.status_code, 409)

    def test_post_queues_a_build(self):
        publish(self.map)
        with mock.patch("geonode.zalf.tasks.build_download_package.apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url(), **basic_auth("pkg-admin"))
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["started"])
        apply_async.assert_called_once()

    def test_anonymous_downloads_a_ready_package(self):
        dataset = self.dataset("ds", [self.file("a.shp", b"shape")])
        publish(self.map)
        publish(dataset)
        package = self.build()

        state = self.client.get(self.url()).json()
        self.assertTrue(state["ready"])
        self.assertTrue(state["download_url"].endswith(self.url("download/")))
        self.assertNotIn("error", state)  # internal fields are for data stewards only

        response = self.client.get(self.url("download/"))
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content) if response.streaming else response.content
        self.assertTrue(zipfile.ZipFile(io.BytesIO(body)).namelist())
        self.assertEqual(ResourceBase.objects.get(pk=self.map.pk).download_count, 1)
        self.assertEqual(package.state, DownloadPackage.STATE_READY)

    def test_download_without_package_is_404(self):
        publish(self.map)
        self.assertEqual(self.client.get(self.url("download/")).status_code, 404)


@override_settings(
    ZALF_DOWNLOAD_S3_BUCKET="packages",
    ZALF_DOWNLOAD_S3_ENDPOINT_URL="https://fsn1.your-objectstorage.com",
    ZALF_DOWNLOAD_S3_REGION="fsn1",
    ZALF_DOWNLOAD_S3_PREFIX="download-packages",
    ZALF_DOWNLOAD_S3_PUBLIC=False,
    ZALF_DOWNLOAD_S3_URL_EXPIRY=600,
)
class TestS3AssetHandler(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("s3-owner", "s@example.test", "pw")
        self.client_mock = mock.MagicMock()
        self.client_mock.generate_presigned_url.return_value = "https://signed.example/obj"
        patcher = mock.patch("geonode.zalf.s3_assets.s3_client", return_value=self.client_mock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.handler = S3AssetHandler()

    def create(self):
        with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
            return self.handler.create(
                "Download package",
                "",
                "download_package",
                self.owner,
                files=[tmp.name],
                content_type="application/zip",
                download_name="collection-1.zip",
                size=10,
                sha256="abc",
            )

    def test_create_uploads_under_a_fresh_key_as_an_attachment(self):
        asset = self.create()
        args, kwargs = self.client_mock.upload_file.call_args
        self.assertEqual(args[1], "packages")
        self.assertTrue(args[2].startswith("download-packages/") and args[2].endswith("/collection-1.zip"))
        self.assertEqual(kwargs["ExtraArgs"]["ContentDisposition"], 'attachment; filename="collection-1.zip"')
        self.assertNotIn("ACL", kwargs["ExtraArgs"])
        self.assertEqual((asset.bucket, asset.key, asset.size, asset.sha256), ("packages", args[2], 10, "abc"))

    def test_download_redirects_to_a_presigned_url(self):
        asset = self.create()
        response = S3AssetDownloadHandler().create_response(asset, attachment=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://signed.example/obj")
        self.client_mock.generate_presigned_url.assert_called_once_with(
            "get_object", Params={"Bucket": "packages", "Key": asset.key}, ExpiresIn=600
        )

    def test_public_mode_redirects_to_the_object_url(self):
        asset = self.create()
        self.client_mock.meta.endpoint_url = "https://fsn1.your-objectstorage.com"
        with override_settings(ZALF_DOWNLOAD_S3_PUBLIC=True):
            response = S3AssetDownloadHandler().create_response(asset)
        self.assertEqual(response["Location"], f"https://fsn1.your-objectstorage.com/packages/{asset.key}")

    def test_deleting_the_asset_deletes_the_object(self):
        asset = self.create()
        key = asset.key
        asset.delete()
        self.client_mock.delete_object.assert_called_once_with(Bucket="packages", Key=key)

    def test_clone_copies_server_side(self):
        asset = self.create()
        clone = self.handler.clone(asset)
        self.assertNotEqual(clone.key, asset.key)
        self.assertEqual(self.client_mock.copy.call_args.args[0], {"Bucket": "packages", "Key": asset.key})


@override_settings(
    ZALF_DOWNLOAD_S3_BUCKET="packages",
    ZALF_DOWNLOAD_S3_ENDPOINT_URL="https://fsn1.your-objectstorage.com",
    ZALF_DOWNLOAD_S3_REGION="fsn1",
    ZALF_DOWNLOAD_S3_ADDRESSING_STYLE="virtual",
)
class TestS3Client(TestCase):
    def test_client_targets_the_endpoint_and_sends_checksums_only_when_required(self):
        from geonode.zalf import s3_assets

        with mock.patch("boto3.client") as boto_client:
            s3_assets.s3_client()
        kwargs = boto_client.call_args.kwargs
        self.assertEqual(kwargs["endpoint_url"], "https://fsn1.your-objectstorage.com")
        self.assertEqual(kwargs["region_name"], "fsn1")
        self.assertEqual(kwargs["config"].signature_version, "s3v4")
        self.assertEqual(kwargs["config"].request_checksum_calculation, "when_required")
        self.assertEqual(kwargs["config"].response_checksum_validation, "when_required")


class TestBuildCommand(PackageTestBase):
    def test_sync_builds_published_maps_and_skips_unpublished_ones(self):
        from django.core.management import call_command

        dataset = self.dataset("ds", [self.file("a.shp")])
        publish(self.map)
        publish(dataset)
        other = Map.objects.create(owner=self.owner, title="Draft")
        ResourceBase.objects.filter(pk=other.pk).update(is_published=False)
        out, err = io.StringIO(), io.StringIO()

        call_command(
            "build_download_packages", "--map", str(self.map.pk), str(other.pk), "--sync", stdout=out, stderr=err
        )

        self.assertIn(f"Map {self.map.pk}: ready", out.getvalue())
        self.assertIn(str(other.pk), err.getvalue())
        self.assertTrue(DownloadPackage.objects.get(map=self.map).is_ready)
        self.assertFalse(DownloadPackage.objects.filter(map=other).exists())

    def test_requires_a_selection(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("build_download_packages")
