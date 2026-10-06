import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from geonode.layers.models import Dataset
from geonode.zalf.delivery_audit import DatasetDeliveryAuditor, DeliveryAuditUnavailable, _is_exception_body
from geonode.zalf.delivery_audit_scheduler import schedule_delivery_audit
from geonode.zalf.models import DatasetDeliveryAudit
from geonode.zalf.tasks import audit_dataset_delivery

AUDIT_SETTINGS = {
    "ZALF_DELIVERY_AUDIT_REQUEST_TIMEOUT": 5,
    "ZALF_DELIVERY_AUDIT_GRIDSET": "EPSG:3857x2",
    "ZALF_DELIVERY_AUDIT_FORMAT": "image/png8",
    "ZALF_DELIVERY_AUDIT_TILE_SIZE": 512,
    "ZALF_DELIVERY_AUDIT_META_FACTOR": 2,
    "ZALF_DELIVERY_AUDIT_TILE_ZOOM": 1,
    "ZALF_DELIVERY_AUDIT_GEOMETRY_SAMPLE": 10,
    "ZALF_DELIVERY_AUDIT_SEED_ENABLED": False,
    "ZALF_DELIVERY_AUDIT_SEED_MIN_ZOOM": 0,
    "ZALF_DELIVERY_AUDIT_SEED_MAX_ZOOM": 1,
    "ZALF_DELIVERY_AUDIT_SEED_MAX_TILES": 10,
}


def response(status=200, content=b"", content_type="application/xml", **headers):
    result = MagicMock()
    result.status_code = status
    result.content = content
    result.headers = {"content-type": content_type, **headers}
    return result


def dataset_stub():
    return SimpleNamespace(
        pk=42,
        workspace="geonode",
        name="test_layer",
        subtype="vector",
        default_style=SimpleNamespace(name="geonode:test_style"),
        ll_bbox=[13.0, 14.0, 52.0, 53.0, "EPSG:4326"],
        get_self_resource=lambda: object(),
        is_vector=lambda: True,
    )


LAYER_XML = b"<layer><enabled>true</enabled><advertised>true</advertised></layer>"
GWC_XML = b"""<GeoServerLayer>
  <enabled>true</enabled><metaWidthHeight><int>2</int><int>2</int></metaWidthHeight>
  <mimeFormats><string>image/png8</string></mimeFormats>
  <gridSubsets><gridSubset><gridSetName>EPSG:3857x2</gridSetName></gridSubset></gridSubsets>
  <parameterFilters><styleParameterFilter><key>STYLES</key><defaultValue></defaultValue>
    <string>geonode:test_style</string></styleParameterFilter></parameterFilters>
</GeoServerLayer>"""
GRID_XML = b"""<gridSet><name>EPSG:3857x2</name>
  <extent><coords><double>-20037508.342789244</double><double>-20037508.342789244</double>
  <double>20037508.342789244</double><double>20037508.342789244</double></coords></extent>
  <tileWidth>512</tileWidth><tileHeight>512</tileHeight>
  <resolutions><double>78271.51696402048</double><double>39135.75848201024</double></resolutions>
</gridSet>"""


@override_settings(**AUDIT_SETTINGS)
class DeliveryAuditorTests(SimpleTestCase):
    def _auditor(self):
        session = MagicMock()

        def get(url, **kwargs):
            if "/gwc/rest/layers/" in url:
                return response(content=GWC_XML)
            if "/gwc/rest/gridsets/" in url:
                return response(content=GRID_XML)
            if "/rest/layers/" in url:
                return response(content=LAYER_XML)
            if url.endswith("/wms"):
                return response(
                    content=b"\x89PNG\r\n",
                    content_type="image/png",
                    **{"geowebcache-cache-result": "MISS"},
                )
            if url.endswith("/wfs"):
                return response(content=b'{"type":"FeatureCollection","features":[]}', content_type="application/json")
            raise AssertionError(url)

        session.get.side_effect = get
        return DatasetDeliveryAuditor(dataset_stub(), session=session)

    @patch("geonode.zalf.delivery_audit.geofence.get_rules")
    @patch("geonode.zalf.delivery_audit.permissions_registry.get_perms", return_value=["view_resourcebase"])
    @patch("geonode.zalf.delivery_audit.get_anonymous_user", return_value=SimpleNamespace())
    def test_success_records_explicit_cache_miss(self, anonymous, permissions, rules):
        rules.return_value = {
            "rules": [
                {"access": "ALLOW", "service": "WMS"},
                {"access": "ALLOW", "service": "WFS"},
            ]
        }
        auditor = self._auditor()
        auditor.check_postgis = lambda: auditor._record("postgis", True, {"spatial_index": True})
        with patch.dict(settings.OGC_SERVER["default"], {"GEOFENCE_SECURITY_ENABLED": True}):
            result = auditor.run()

        self.assertEqual(result["status"], "passed")
        wms = next(item for item in result["checks"] if item["name"] == "anonymous_wms")
        self.assertEqual(wms["details"]["cache_result"], "MISS")
        self.assertFalse(result["seed"]["enabled"])
        self.assertFalse(result["policy"]["style_mutation"])

    @patch("geonode.zalf.delivery_audit.geofence.get_rules", return_value={"rules": []})
    @patch("geonode.zalf.delivery_audit.permissions_registry.get_perms", return_value=["view_resourcebase"])
    @patch("geonode.zalf.delivery_audit.get_anonymous_user", return_value=SimpleNamespace())
    def test_missing_geofence_rules_fails(self, anonymous, permissions, rules):
        auditor = self._auditor()
        with patch.dict(settings.OGC_SERVER["default"], {"GEOFENCE_SECURITY_ENABLED": True}):
            auditor.check_permissions()
        self.assertEqual(auditor.checks[0]["status"], "failed")

    def test_exception_xml_is_not_a_valid_http_200(self):
        error = response(
            content=b"<ServiceExceptionReport><ServiceException>bad</ServiceException></ServiceExceptionReport>",
            content_type="application/xml",
        )
        self.assertTrue(_is_exception_body(error))

    def test_gwc_gridset_mismatch_fails(self):
        auditor = self._auditor()
        auditor.session.get.side_effect = lambda url, **kwargs: response(
            content=GWC_XML.replace(b"EPSG:3857x2", b"EPSG:4326")
        )
        self.assertIsNone(auditor.check_gwc())
        self.assertEqual(auditor.checks[-1]["status"], "failed")

    def test_wms_without_cache_result_is_reported_as_gwc_bypass(self):
        auditor = self._auditor()
        grid = auditor.check_gwc()
        original = auditor.session.get.side_effect

        def without_cache_header(url, **kwargs):
            if url.endswith("/wms"):
                return response(content=b"\x89PNG\r\n", content_type="image/png")
            return original(url, **kwargs)

        auditor.session.get.side_effect = without_cache_header
        auditor.check_anonymous_ows(grid)
        wms = next(item for item in auditor.checks if item["name"] == "anonymous_wms")
        self.assertEqual(wms["status"], "failed")
        self.assertIsNone(wms["details"]["cache_result"])

    @patch("geonode.zalf.delivery_audit.connections")
    def test_postgis_reports_bounded_complexity_and_index(self, connections):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            ("public", "geom", 25833, "MULTIPOLYGON"),
            (True,),
            (288938, SimpleNamespace(isoformat=lambda: "2026-10-06T00:00:00Z"), None),
            (10, 1200, 345.5),
        ]
        connection.ops.quote_name.side_effect = lambda value: f'"{value}"'
        connections.__getitem__.return_value = connection
        auditor = self._auditor()
        auditor.check_postgis()
        check = auditor.checks[-1]
        self.assertEqual(check["status"], "passed")
        self.assertEqual(check["details"]["source_srid"], 25833)
        self.assertEqual(check["details"]["sample_limit"], 10)
        self.assertEqual(check["details"]["sample_max_points"], 1200)
        complexity_sql = cursor.execute.call_args_list[-1].args[0]
        self.assertIn("LIMIT %s", complexity_sql)

    @override_settings(
        **{
            **AUDIT_SETTINGS,
            "ZALF_DELIVERY_AUDIT_SEED_ENABLED": True,
            "ZALF_DELIVERY_AUDIT_SEED_MAX_TILES": 1,
        }
    )
    def test_seed_refuses_extent_over_tile_budget(self):
        auditor = self._auditor()
        grid = auditor.check_gwc()
        result = auditor.seed_if_enabled(grid)
        self.assertFalse(result["submitted"])
        self.assertEqual(result["reason"], "tile budget exceeded")
        auditor.session.post.assert_not_called()


@override_settings(**AUDIT_SETTINGS)
class DeliveryAuditTaskTests(TestCase):
    fixtures = ["initial_data.json", "group_test_data.json", "default_oauth_apps.json"]

    def setUp(self):
        self.owner = get_user_model().objects.create_user(username=f"audit-{uuid.uuid4().hex[:8]}")

    def create_dataset(self, **kwargs):
        subtype = kwargs.pop("subtype", "vector")
        with patch("geonode.zalf.signals.schedule_delivery_audit"):
            return Dataset.objects.create(
                owner=self.owner,
                title="Audit dataset",
                name=f"audit_{uuid.uuid4().hex[:8]}",
                workspace="geonode",
                store="datastore",
                subtype=subtype,
                **kwargs,
            )

    @patch("geonode.zalf.delivery_audit_scheduler.transaction.on_commit")
    def test_schedule_is_idempotent_and_after_commit(self, on_commit):
        dataset = self.create_dataset(is_approved=True, is_published=True)
        self.assertTrue(schedule_delivery_audit(dataset))
        self.assertFalse(schedule_delivery_audit(dataset))
        self.assertEqual(on_commit.call_count, 1)
        on_commit.call_args.args[0]

    def test_signal_fires_once_only_on_ready_transition(self):
        dataset = self.create_dataset(is_approved=False, is_published=False)
        with patch("geonode.zalf.signals.schedule_delivery_audit") as schedule:
            dataset.is_approved = True
            dataset.is_published = True
            dataset.save(update_fields=["is_approved", "is_published"])
            dataset.title = "Unrelated update"
            dataset.save(update_fields=["title"])
        schedule.assert_called_once_with(dataset)

    def test_private_and_non_spatial_resources_are_skipped(self):
        private = self.create_dataset(is_approved=True, is_published=False)
        result = audit_dataset_delivery.run(private.pk)
        self.assertEqual(result["status"], "skipped")

        tabular = self.create_dataset(is_approved=True, is_published=True, subtype="tabular")
        result = audit_dataset_delivery.run(tabular.pk)
        self.assertEqual(result["status"], "skipped")

    def test_deleted_resource_is_skipped(self):
        result = audit_dataset_delivery.run(99999999)
        self.assertEqual(result, {"dataset_id": 99999999, "status": "skipped", "reason": "deleted"})

    @patch("geonode.zalf.tasks.DatasetDeliveryAuditor")
    def test_transient_failure_keeps_retryable_pending_state(self, auditor_class):
        dataset = self.create_dataset(is_approved=True, is_published=True)
        auditor_class.return_value.run.side_effect = DeliveryAuditUnavailable("GeoServer unavailable")
        with self.assertRaises(DeliveryAuditUnavailable):
            audit_dataset_delivery.run(dataset.pk)
        audit = DatasetDeliveryAudit.objects.get(dataset=dataset)
        self.assertEqual(audit.status, DatasetDeliveryAudit.Status.PENDING)
        self.assertEqual(audit.result["status"], "retrying")

    @patch("geonode.zalf.tasks.DatasetDeliveryAuditor")
    def test_success_updates_one_machine_readable_record(self, auditor_class):
        dataset = self.create_dataset(is_approved=True, is_published=True)
        auditor_class.return_value.run.return_value = {
            "schema_version": 1,
            "dataset_id": dataset.pk,
            "layer": f"geonode:{dataset.name}",
            "status": "passed",
            "failed_checks": [],
            "checks": [],
        }
        audit_dataset_delivery.run(dataset.pk)
        audit_dataset_delivery.run(dataset.pk)
        audit = DatasetDeliveryAudit.objects.get(dataset=dataset)
        self.assertEqual(DatasetDeliveryAudit.objects.filter(dataset=dataset).count(), 1)
        self.assertEqual(audit.status, DatasetDeliveryAudit.Status.PASSED)
        self.assertEqual(audit.attempt_count, 2)

    def test_machine_readable_endpoint_is_owner_only(self):
        dataset = self.create_dataset(is_approved=True, is_published=True)
        DatasetDeliveryAudit.objects.create(
            dataset=dataset,
            status=DatasetDeliveryAudit.Status.PASSED,
            result={"schema_version": 1, "status": "passed", "checks": []},
        )
        url = reverse("dataset_delivery_audit", kwargs={"dataset_id": dataset.pk})

        stranger = get_user_model().objects.create_user(username=f"stranger-{uuid.uuid4().hex[:8]}")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.owner)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["schema_version"], 1)
