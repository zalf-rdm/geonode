from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from geonode.base.models import ResearchDomain, ResourceBase
from geonode.metadata.handlers.zalf import ZalfHandler


class ZalfResearchDomainHandlerTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(
            username="research-domain-owner",
            email="owner@example.com",
        )
        self.resource = ResourceBase.objects.create(
            title="Research domain resource",
            uuid=str(uuid4()),
            owner=owner,
        )
        self.domain = ResearchDomain.objects.create(
            name="Soil Science",
            description="Research focused on soils.",
            order_id=2,
        )
        self.handler = ZalfHandler()

    def test_research_domains_round_trip_without_nested_creation(self):
        errors = {}
        self.handler.update_resource(
            self.resource,
            "research_domains",
            {
                "research_domains": [
                    {
                        "name": self.domain.name,
                        "description": self.domain.description,
                        "order_id": self.domain.order_id,
                    }
                ]
            },
            {},
            errors,
        )

        self.assertEqual(errors, {})
        self.assertEqual(
            self.handler.get_jsonschema_instance(
                self.resource,
                "research_domains",
                {},
                errors,
            ),
            [
                {
                    "name": self.domain.name,
                    "description": self.domain.description,
                    "order_id": self.domain.order_id,
                }
            ],
        )
        self.assertEqual(ResearchDomain.objects.count(), 1)

    def test_missing_research_domain_is_reported(self):
        errors = {}

        self.handler.update_resource(
            self.resource,
            "research_domains",
            {"research_domains": [{"name": "Missing domain"}]},
            {},
            errors,
        )

        self.assertIn("research_domains", errors)
        self.assertEqual(self.resource.research_domains.count(), 0)
        self.assertEqual(ResearchDomain.objects.count(), 1)


class ZalfMetadataLicenseHandlerTests(TestCase):
    """Metadata License in the GN5 metadata editor (zalf-rdm/geonode#810)."""

    def setUp(self):
        from geonode.base.models import License

        owner = get_user_model().objects.create_user(username="metadata-license-owner", email="ml@example.com")
        self.resource = ResourceBase.objects.create(title="Metadata license resource", uuid=str(uuid4()), owner=owner)
        self.license = License.objects.create(identifier="test-cc0", name="Test CC0")
        self.handler = ZalfHandler()

    def test_schema_has_metadata_license_with_license_autocomplete(self):
        schema = self.handler.update_schema({"properties": {"license": {}}}, {}, None)
        subschema = schema["properties"]["metadata_license"]
        self.assertEqual(subschema["geonode:handler"], "zalf")
        self.assertIn("geonode-ui:autocomplete", subschema["ui:options"])
        self.assertTrue(subschema["ui:options"]["geonode-ui:autocomplete"].endswith("licenses"))
        # placed right after "license"
        keys = list(schema["properties"])
        self.assertEqual(keys.index("metadata_license"), keys.index("license") + 1)

    def test_metadata_license_round_trip(self):
        errors, context = {}, {}
        self.handler.update_resource(
            self.resource,
            "metadata_license",
            {"metadata_license": {"id": "test-cc0", "label": "Test CC0"}},
            context,
            errors,
        )
        self.assertEqual(errors, {})
        self.assertEqual(context["base"]["metadata_license"], self.license)
        self.assertEqual(
            self.handler.get_jsonschema_instance(self.resource, "metadata_license", {}, errors),
            {"id": "test-cc0", "label": "Test CC0"},
        )

    def test_metadata_license_can_be_cleared(self):
        self.resource.metadata_license = self.license
        errors, context = {}, {}
        self.handler.update_resource(self.resource, "metadata_license", {"metadata_license": None}, context, errors)
        self.assertEqual(errors, {})
        self.assertIsNone(context["base"]["metadata_license"])
        self.assertIsNone(self.handler.get_jsonschema_instance(self.resource, "metadata_license", {}, errors))

    def test_unknown_license_is_reported(self):
        errors = {}
        self.handler.update_resource(
            self.resource, "metadata_license", {"metadata_license": {"id": "does-not-exist"}}, {}, errors
        )
        self.assertIn("metadata_license", errors)


class ZalfCategoryOptionalTests(TestCase):
    """Category is optional in the ZALF metadata schema (zalf-rdm/geonode#810)."""

    def test_category_is_not_required(self):
        from geonode.metadata.manager import metadata_manager

        schema = metadata_manager.build_schema()
        self.assertIn("category", schema["properties"])
        self.assertNotIn("category", schema.get("required", []))
        self.assertIn("license", schema.get("required", []))
