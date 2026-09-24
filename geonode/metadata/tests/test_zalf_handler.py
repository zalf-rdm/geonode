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
