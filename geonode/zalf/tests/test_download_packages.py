"""
Tests for map download packages (zalf-rdm/geonode#659).

The packages are built and stored as LocalAssets here (no S3 bucket configured);
the S3 handler is tested on its own against a mocked boto3 client, since moto is
not a dependency and real providers (Hetzner) are smoke-tested by hand.
"""

import base64
import datetime
import hashlib
import io
import os
import shutil
import tempfile
import zipfile
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from geonode.assets.utils import create_asset_and_link, get_default_asset
from geonode.base.models import LinkedResource, ResourceBase
from geonode.base.populate_test_data import create_single_dataset, create_single_doc
from geonode.maps.models import Map, MapLayer
from geonode.zalf import download_package_checks as checks
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
    "ZALF_DOWNLOAD_PACKAGE_ENABLED": True,
}

# A fixed timestamp for mocked S3 listings, which the report formats as a date.
NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.timezone.utc)


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
        self.assertTrue(response.json()["enabled"])

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


class TestActivationSwitch(PackageTestBase):
    """ZALF_DOWNLOAD_PACKAGE_ENABLED=False takes the whole feature out of use."""

    def setUp(self):
        # After super(), which enables ENV with the feature on.
        super().setUp()
        self.switch_off = override_settings(ZALF_DOWNLOAD_PACKAGE_ENABLED=False)
        self.switch_off.enable()

    def tearDown(self):
        self.switch_off.disable()
        super().tearDown()

    def url(self, suffix=""):
        return f"/api/v2/maps/{self.map.pk}/download_package/{suffix}"

    def test_request_build_queues_nothing(self):
        with mock.patch("geonode.zalf.tasks.build_download_package.apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                package, started = download_packages.request_build(self.map, user=self.admin)
        self.assertFalse(started)
        self.assertIsNone(package)
        self.assertFalse(DownloadPackage.objects.exists())
        apply_async.assert_not_called()

    def test_a_build_queued_before_the_switch_was_flipped_is_dropped(self):
        DownloadPackage.objects.create(map=self.map, state=DownloadPackage.STATE_PENDING)
        package = download_packages.run_build(self.map.pk, task_id="test")
        self.assertEqual(package.state, DownloadPackage.STATE_FAILED)
        self.assertIn("ZALF_DOWNLOAD_PACKAGE_ENABLED", package.error)
        self.assertIsNone(package.asset_id)

    def test_publication_does_not_queue_a_build(self):
        from geonode.zalf.api import views

        dataset = self.dataset("pub", [self.file("a.shp")])
        ResourceBase.objects.filter(pk=dataset.pk).update(is_approved=True)
        dataset.refresh_from_db()
        serializer = PublishSerializer(
            data={"owner": self.owner.pk, "resources": [dataset.pk], "doi_prefix": "10.1234"}
        )
        serializer.is_valid(raise_exception=True)
        with (
            mock.patch.object(views, "validate_doi_prefix"),
            mock.patch.object(views, "get_datacite_account_for_prefix"),
            mock.patch.object(views, "register_doi", return_value="10.1234/x"),
            mock.patch.object(download_packages, "request_build") as request_build,
        ):
            response = views._publish_data_collection(self.map, serializer.validated_data, user=self.admin)
        request_build.assert_not_called()
        self.assertNotIn("download_package", response)

    def test_the_api_reports_the_feature_as_off(self):
        publish(self.map)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["enabled"])
        self.assertIsNone(response.json()["state"])
        self.assertEqual(self.client.post(self.url(), **basic_auth("pkg-admin")).status_code, 409)

    def test_a_package_built_before_is_not_served(self):
        dataset = self.dataset("ds", [self.file("a.shp", b"shape")])
        publish(self.map)
        publish(dataset)
        with override_settings(ZALF_DOWNLOAD_PACKAGE_ENABLED=True):
            package = self.build()
        self.assertEqual(package.state, DownloadPackage.STATE_READY)
        self.assertEqual(self.client.get(self.url("download/")).status_code, 404)
        self.assertIsNone(self.client.get(self.url()).json()["state"])

    def test_the_build_command_declines(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaisesMessage(CommandError, "ZALF_DOWNLOAD_PACKAGE_ENABLED"):
            call_command("build_download_packages", "--all-published")

    def test_the_status_command_still_reports(self):
        from django.core.management import call_command

        publish(self.map)
        out = io.StringIO()
        call_command("download_package_status", stdout=out)
        self.assertIn("1 published data collections: 1 missing", out.getvalue())
        self.assertIn("switched off", out.getvalue())

    def test_the_admin_action_queues_nothing(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from geonode.zalf.admin import DownloadPackageAdmin

        DownloadPackage.objects.create(map=self.map)
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        request._messages = mock.MagicMock()
        with mock.patch("geonode.zalf.tasks.build_download_package.apply_async") as apply_async:
            DownloadPackageAdmin(DownloadPackage, AdminSite()).rebuild(request, DownloadPackage.objects.all())
        apply_async.assert_not_called()
        self.assertIn("switched off", str(request._messages.add.call_args))


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


class TestStatusCommand(PackageTestBase):
    def two_collections(self):
        """One published map with no package, one with a failed build, one unpublished."""
        publish(self.map)
        failed = Map.objects.create(owner=self.owner, title="Broken Collection")
        publish(failed)
        DownloadPackage.objects.create(map=failed, state=DownloadPackage.STATE_FAILED, error="Traceback\nboom")
        draft = Map.objects.create(owner=self.owner, title="Draft")
        ResourceBase.objects.filter(pk=draft.pk).update(is_published=False)
        return failed

    def status(self, *args):
        out = io.StringIO()
        call_command("download_package_status", *args, stdout=out)
        return out.getvalue()

    def build_one(self):
        DownloadPackage.objects.get_or_create(map=self.map)
        package = download_packages.run_build(self.map.pk)
        self.assertEqual(package.state, DownloadPackage.STATE_READY, package.error)
        return package

    def test_lists_published_maps_with_their_package_state(self):
        failed = self.two_collections()

        output = self.status()

        self.assertRegex(output, rf"{self.map.pk}\s+missing .*Soil Collection")
        self.assertRegex(output, rf"{failed.pk}\s+failed .*Broken Collection")
        self.assertNotIn("Draft", output)
        self.assertIn("2 published data collections: 1 missing, 1 failed", output)

    def test_broken_only_lists_just_the_rows_needing_attention(self):
        failed = self.two_collections()

        output = self.status("--broken-only")

        self.assertRegex(output, rf"{failed.pk}\s+failed .*Broken Collection")
        self.assertIn("boom", output)
        # A map with no package has not failed, so it does not need attention.
        self.assertNotIn("Soil Collection", output)
        # The summary still describes every collection, not the printed rows.
        self.assertIn("2 published data collections: 1 missing, 1 failed", output)

    def test_broken_only_says_so_when_nothing_is_broken(self):
        publish(self.map)

        output = self.status("--broken-only")

        self.assertIn("No packages need attention", output)
        self.assertIn("1 published data collections: 1 missing", output)

    def test_a_failure_that_recorded_no_message_still_reports(self):
        failed = Map.objects.create(owner=self.owner, title="Quietly Broken")
        publish(failed)
        DownloadPackage.objects.create(map=failed, state=DownloadPackage.STATE_FAILED, error="")

        output = self.status("--broken-only")

        self.assertIn("no error recorded", output)

    def test_state_filters_to_one_status(self):
        dataset = self.dataset("ds", [self.file("a.shp", b"shape")])
        publish(self.map)
        publish(dataset)
        DownloadPackage.objects.create(map=self.map)
        download_packages.run_build(self.map.pk)
        other = Map.objects.create(owner=self.owner, title="No Package Here")
        publish(other)

        output = self.status("--state", "missing")

        self.assertIn("No Package Here", output)
        self.assertNotIn("Soil Collection", output)
        self.assertIn("2 published data collections: 1 ok, 1 missing", output)

    def test_db_only_skips_the_storage_and_says_so(self):
        """The cheap listing: the row's own view, with no request to the bucket."""
        dataset = self.dataset("ds", [self.file("a.shp", b"shape")])
        publish(self.map)
        publish(dataset)
        package = self.build_one()
        # The file is gone, but --db-only cannot know that and must not claim to.
        os.remove(package.asset.get_real_instance().location[0])

        output = self.status("--db-only")

        self.assertIn("ready", output)
        self.assertNotIn("gone", output)
        self.assertIn("storage was not asked", output)

        # Without --db-only the same repository reports the truth.
        self.assertIn("gone", self.status())

    def test_db_only_refuses_the_flags_that_need_the_storage(self):
        from django.core.management.base import CommandError

        publish(self.map)
        for flag in ("--deep", "--orphans"):
            with self.assertRaisesMessage(CommandError, "both need the storage"):
                self.status("--db-only", flag)


class TestValidation(PackageTestBase):
    """
    `download_package_checks`: the storage, not the row, decides whether a
    package is available (zalf-rdm/geonode#659). Local assets here; the S3 path
    has its own class below.
    """

    def ready_package(self):
        dataset = self.dataset("ds", [self.file("a.shp", b"shape")])
        publish(self.map)
        # The package holds what the publication made public, so the dataset has
        # to be published too or the build has nothing to put in it.
        publish(dataset)
        package = self.build()
        self.assertEqual(package.state, DownloadPackage.STATE_READY, package.error)
        return package

    def path_of(self, package):
        return package.asset.get_real_instance().location[0]

    def check(self, package=None, **kwargs):
        return checks.check_package(package or DownloadPackage.objects.get(map=self.map), **kwargs)

    def test_a_built_package_is_available(self):
        package = self.ready_package()
        result = self.check(package)
        self.assertEqual(result.status, checks.OK)
        self.assertTrue(result.is_ok)
        self.assertFalse(result.is_broken)
        self.assertEqual(result.stored_size, package.size)
        self.assertEqual(result.location, self.path_of(package))

    def test_a_file_that_is_gone_is_reported_gone(self):
        package = self.ready_package()
        os.remove(self.path_of(package))
        result = self.check(package)
        self.assertEqual(result.status, checks.GONE)
        self.assertTrue(result.is_broken)
        self.assertIn("not on disk", result.detail)

    def test_a_size_that_disagrees_with_the_build_is_a_mismatch(self):
        package = self.ready_package()
        with open(self.path_of(package), "ab") as target:
            target.write(b"appended")
        result = self.check(package)
        self.assertEqual(result.status, checks.MISMATCH)
        self.assertIn(str(package.size), result.detail)

    def test_an_empty_file_is_a_mismatch(self):
        package = self.ready_package()
        open(self.path_of(package), "wb").close()
        DownloadPackage.objects.filter(pk=package.pk).update(size=None)
        result = self.check()
        self.assertEqual(result.status, checks.MISMATCH)
        self.assertIn("empty", result.detail)

    def test_a_deep_check_verifies_the_zip_and_the_checksum(self):
        package = self.ready_package()
        result = self.check(package, deep=True)
        self.assertEqual(result.status, checks.OK)
        self.assertIn("sha256 matches", result.detail)

    def test_a_rewritten_package_fails_the_deep_check_only(self):
        package = self.ready_package()
        path = self.path_of(package)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("other.txt", "not what was built")
        # Same bookkeeping, different bytes: only reading it notices.
        DownloadPackage.objects.filter(pk=package.pk).update(size=os.path.getsize(path))
        self.assertEqual(self.check().status, checks.OK)
        result = self.check(deep=True)
        self.assertEqual(result.status, checks.MISMATCH)
        self.assertIn("sha256", result.detail)

    def test_a_file_that_is_not_a_zip_is_corrupt(self):
        package = self.ready_package()
        path = self.path_of(package)
        with open(path, "wb") as target:
            target.write(b"not a zip at all")
        DownloadPackage.objects.filter(pk=package.pk).update(size=os.path.getsize(path), sha256="")
        result = self.check(deep=True)
        self.assertEqual(result.status, checks.CORRUPT)
        self.assertIn("not a readable ZIP", result.detail)

    def test_a_deep_check_skips_a_package_over_the_size_limit(self):
        package = self.ready_package()
        result = self.check(package, deep=True, max_deep_bytes=1)
        self.assertEqual(result.status, checks.OK)
        self.assertIn("deep check skipped", result.detail)

    def test_ready_without_an_asset_is_broken(self):
        package = self.ready_package()
        asset = package.asset.get_real_instance()
        DownloadPackage.objects.filter(pk=package.pk).update(asset=None)
        asset.delete()
        result = self.check()
        self.assertEqual(result.status, checks.NO_ASSET)
        self.assertIn("no asset is linked", result.detail)

    def test_a_failed_build_is_reported_with_its_error(self):
        DownloadPackage.objects.create(
            map=self.map, state=DownloadPackage.STATE_FAILED, error="Traceback…\nboom: it broke"
        )
        result = self.check()
        self.assertEqual(result.status, checks.FAILED)
        self.assertEqual(result.detail, "boom: it broke")

    def test_a_running_build_is_pending_not_broken(self):
        DownloadPackage.objects.create(map=self.map, state=DownloadPackage.STATE_BUILDING)
        result = self.check()
        self.assertEqual(result.status, checks.PENDING)
        self.assertFalse(result.is_broken)

    def test_a_build_whose_worker_died_is_stale(self):
        package = DownloadPackage.objects.create(map=self.map, state=DownloadPackage.STATE_BUILDING)
        dead = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            seconds=settings.ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT + 60
        )
        DownloadPackage.objects.filter(pk=package.pk).update(updated_at=dead)
        result = self.check()
        self.assertEqual(result.status, checks.STALE)
        self.assertTrue(result.is_broken)
        self.assertIn("the worker died", result.detail)

    def test_a_published_collection_without_a_package_is_missing(self):
        publish(self.map)
        results = checks.check_packages(include_missing=True)
        self.assertEqual([(r.map_id, r.status) for r in results], [(self.map.pk, checks.MISSING)])
        # Without include_missing there is simply nothing to report.
        self.assertEqual(checks.check_packages(), [])

    def test_the_report_puts_the_worst_rows_first(self):
        other = Map.objects.create(owner=self.owner, title="Second")
        other.set_default_permissions()
        self.ready_package()
        DownloadPackage.objects.create(map=other, state=DownloadPackage.STATE_FAILED, error="boom")
        statuses = [result.status for result in checks.check_packages()]
        self.assertEqual(statuses, [checks.FAILED, checks.OK])
        self.assertEqual(checks.summarize(checks.check_packages()), {checks.OK: 1, checks.FAILED: 1})

    def status(self, *args):
        out = io.StringIO()
        call_command("download_package_status", *args, stdout=out)
        return out.getvalue()

    def test_the_command_checks_the_storage_by_default(self):
        self.ready_package()
        output = self.status()
        self.assertIn(f"{self.map.pk}", output)
        self.assertIn("ok", output)
        self.assertIn("1 published data collections: 1 ok", output)
        self.assertIn("every package is available", output)

    def test_the_command_can_fail_on_broken_for_cron(self):
        package = self.ready_package()
        os.remove(self.path_of(package))
        # Without the flag it reports and still exits cleanly.
        self.assertIn("need attention", self.status())
        with self.assertRaises(SystemExit):
            self.status("--fail-on-broken")

    def test_the_command_can_show_only_what_needs_attention(self):
        self.ready_package()
        other = Map.objects.create(owner=self.owner, title="Second")
        publish(other)
        DownloadPackage.objects.create(map=other, state=DownloadPackage.STATE_FAILED, error="boom")
        output = self.status("--broken-only")
        self.assertIn("Second", output)
        self.assertNotIn("Soil Collection", output)
        # The summary still counts everything that was checked.
        self.assertIn("2 published data collections", output)

    def test_the_command_checks_one_map_only(self):
        self.ready_package()
        other = Map.objects.create(owner=self.owner, title="Second")
        publish(other)
        DownloadPackage.objects.create(map=other, state=DownloadPackage.STATE_FAILED)
        self.assertIn("1 published data collections: 1 failed", self.status("--map", str(other.pk)))

    def test_the_command_still_reports_while_the_feature_is_off(self):
        self.ready_package()
        with override_settings(ZALF_DOWNLOAD_PACKAGE_ENABLED=False):
            output = self.status()
        self.assertIn("switched off", output)
        self.assertIn("1 ok", output)

    def test_the_admin_page_lists_every_package(self):
        self.ready_package()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:zalf_downloadpackage_validation"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Download package validation", body)
        self.assertIn("Soil Collection", body)
        self.assertIn("status-ok", body)

    def test_the_admin_page_marks_a_broken_package(self):
        package = self.ready_package()
        os.remove(self.path_of(package))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:zalf_downloadpackage_validation"))
        body = response.content.decode()
        self.assertIn("status-broken", body)
        self.assertIn("need attention", body)

    def test_the_admin_page_is_staff_only(self):
        """
        A user who may not use the admin gets no report. This deployment answers
        404 rather than redirecting to the admin login the way the changelist
        does; what matters is that no row reaches them either way.
        """
        self.client.force_login(self.owner)
        response = self.client.get(reverse("admin:zalf_downloadpackage_validation"))
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn(b"Download package validation", response.content)

    def test_the_admin_action_reports_each_package(self):
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        from geonode.zalf.admin import DownloadPackageAdmin

        package = self.ready_package()
        os.remove(self.path_of(package))
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        DownloadPackageAdmin(DownloadPackage, AdminSite()).validate(
            request, DownloadPackage.objects.filter(pk=package.pk)
        )
        reported = [str(message) for message in request._messages]
        self.assertEqual(len(reported), 1)
        self.assertIn("gone", reported[0])


class TestValidationWithS3(PackageTestBase):
    """The S3 side of validation, against a mocked client (as TestS3AssetHandler does)."""

    def setUp(self):
        super().setUp()
        self.client_mock = mock.MagicMock()
        patcher = mock.patch("geonode.zalf.s3_assets.s3_client", return_value=self.client_mock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.bucket_override = override_settings(ZALF_DOWNLOAD_S3_BUCKET="packages")
        self.bucket_override.enable()
        self.addCleanup(self.bucket_override.disable)

        self.asset = S3Asset.objects.create(
            title="Download package",
            type=download_packages.PACKAGE_ASSET_TYPE,
            owner=self.owner,
            bucket="packages",
            key="download-packages/abc/soil-collection-1.zip",
            size=1024,
            sha256="a" * 64,
        )
        self.package = DownloadPackage.objects.create(
            map=self.map, state=DownloadPackage.STATE_READY, asset=self.asset, size=1024, sha256="a" * 64
        )

    def client_error(self, code):
        from botocore.exceptions import ClientError

        return ClientError({"Error": {"Code": code, "Message": code}}, "HeadObject")

    def check(self, **kwargs):
        return checks.check_package(DownloadPackage.objects.get(pk=self.package.pk), **kwargs)

    def test_an_object_in_the_bucket_is_available(self):
        self.client_mock.head_object.return_value = {
            "ContentLength": 1024,
            "ContentType": "application/zip",
            "ContentDisposition": 'attachment; filename="soil-collection-1.zip"',
        }
        result = self.check()
        self.assertEqual(result.status, checks.OK)
        self.assertEqual(result.location, "s3://packages/download-packages/abc/soil-collection-1.zip")
        self.assertEqual(result.stored_size, 1024)
        self.client_mock.head_object.assert_called_once_with(
            Bucket="packages", Key="download-packages/abc/soil-collection-1.zip"
        )

    def test_a_check_uses_the_short_timeout_client(self):
        self.client_mock.head_object.return_value = {"ContentLength": 1024, "ContentType": "application/zip"}
        self.check()
        from geonode.zalf.s3_assets import s3_client

        s3_client.assert_called_with(for_check=True)

    def test_an_object_that_is_gone_is_reported_gone(self):
        self.client_mock.head_object.side_effect = self.client_error("404")
        result = self.check()
        self.assertEqual(result.status, checks.GONE)
        self.assertIn("not in the bucket", result.detail)

    def test_wrong_credentials_are_unreachable_not_gone(self):
        self.client_mock.head_object.side_effect = self.client_error("AccessDenied")
        result = self.check()
        self.assertEqual(result.status, checks.UNREACHABLE)
        self.assertIn("credentials", result.detail)

    def test_a_bucket_that_cannot_be_reached_is_unreachable(self):
        from botocore.exceptions import EndpointConnectionError

        self.client_mock.head_object.side_effect = EndpointConnectionError(endpoint_url="https://nope.example")
        result = self.check()
        self.assertEqual(result.status, checks.UNREACHABLE)
        self.assertTrue(result.is_broken)

    def test_a_truncated_object_is_a_mismatch(self):
        self.client_mock.head_object.return_value = {"ContentLength": 10, "ContentType": "application/zip"}
        result = self.check()
        self.assertEqual(result.status, checks.MISMATCH)
        self.assertIn("10 bytes", result.detail)

    def test_the_wrong_content_type_is_noted_but_not_broken(self):
        self.client_mock.head_object.return_value = {"ContentLength": 1024, "ContentType": "binary/octet-stream"}
        result = self.check()
        self.assertEqual(result.status, checks.OK)
        self.assertIn("content-type", result.detail)
        self.assertIn("content-disposition", result.detail)

    def test_orphans_are_the_keys_no_asset_references(self):
        self.client_mock.get_paginator.return_value.paginate.return_value = [
            {
                "Contents": [
                    {"Key": self.asset.key, "Size": 1024, "LastModified": "now"},
                    {"Key": "download-packages/stale/old.zip", "Size": 99, "LastModified": "then"},
                    {"Key": "download-packages/", "Size": 0, "LastModified": "then"},
                ]
            }
        ]
        orphans, truncated = checks.find_orphans()
        self.assertFalse(truncated)
        self.assertEqual([orphan["key"] for orphan in orphans], ["download-packages/stale/old.zip"])

    def test_dangling_assets_are_those_no_package_references(self):
        self.assertEqual(checks.find_dangling_assets(), [])
        orphan_asset = S3Asset.objects.create(
            title="Download package",
            type=download_packages.PACKAGE_ASSET_TYPE,
            owner=self.owner,
            bucket="packages",
            key="download-packages/left/behind.zip",
        )
        self.assertEqual([asset.pk for asset in checks.find_dangling_assets()], [orphan_asset.pk])

    def test_the_command_lists_orphans(self):
        self.client_mock.head_object.return_value = {"ContentLength": 1024, "ContentType": "application/zip"}
        self.client_mock.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "download-packages/stale/old.zip", "Size": 99, "LastModified": NOW}]}
        ]
        out = io.StringIO()
        call_command("download_package_status", "--orphans", stdout=out)
        output = out.getvalue()
        self.assertIn("download-packages/stale/old.zip", output)
        self.assertIn("no asset references", output)


class TestMapDeletion(PackageTestBase):
    """
    What becomes of a package when its map goes away (zalf-rdm/geonode#659).

    `ResourceBase.delete()` deletes every asset reachable through a `Link` on
    the resource, and `store_package` creates that link, so the normal path
    cleans up after itself. A queryset delete skips that override.
    """

    def built(self):
        dataset = self.dataset("ds", [self.file("a.shp", b"shape")])
        publish(self.map)
        publish(dataset)
        DownloadPackage.objects.get_or_create(map=self.map)
        package = download_packages.run_build(self.map.pk)
        self.assertEqual(package.state, DownloadPackage.STATE_READY, package.error)
        return package

    def test_deleting_a_map_takes_its_package_and_the_file_with_it(self):
        from geonode.assets.models import Asset

        package = self.built()
        asset_pk = package.asset_id
        path = package.asset.get_real_instance().location[0]
        map_pk = self.map.pk

        self.map.delete()

        self.assertFalse(DownloadPackage.objects.filter(map_id=map_pk).exists())
        self.assertFalse(Asset.objects.filter(pk=asset_pk).exists())
        self.assertFalse(os.path.isfile(path))
        self.assertEqual(checks.find_dangling_assets(), [])

    def test_a_queryset_delete_orphans_the_asset_and_the_check_finds_it(self):
        """
        Django's admin "delete selected" deletes through a queryset, which never
        calls ResourceBase.delete() and so never runs its asset cleanup. The
        package row goes (database cascade) but the file stays, which is the
        realistic way a bucket accumulates packages nothing references.
        """
        from geonode.assets.models import Asset

        package = self.built()
        asset_pk = package.asset_id
        path = package.asset.get_real_instance().location[0]
        map_pk = self.map.pk

        Map.objects.filter(pk=map_pk).delete()

        self.assertFalse(DownloadPackage.objects.filter(map_id=map_pk).exists())
        self.assertTrue(Asset.objects.filter(pk=asset_pk).exists())
        self.assertTrue(os.path.isfile(path))

        dangling = checks.find_dangling_assets()
        self.assertEqual([asset.pk for asset in dangling], [asset_pk])
        self.assertEqual(dangling[0].report_location, path)

    def test_the_report_names_the_orphaned_asset(self):
        package = self.built()
        asset_pk = package.asset_id
        Map.objects.filter(pk=self.map.pk).delete()

        out = io.StringIO()
        call_command("download_package_status", "--orphans", stdout=out)

        output = out.getvalue()
        self.assertIn(f"asset {asset_pk}", output)
        self.assertIn("no DownloadPackage row references", output)
