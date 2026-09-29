from uuid import uuid4

from django.test import RequestFactory, TestCase
from rest_framework.request import Request

from geonode.base.api.filters import DynamicSearchFilter
from geonode.base.models import ContactRole, RelatedProject, ResourceBase
from geonode.people.models import Profile


class DynamicSearchFilterTests(TestCase):
    def setUp(self):
        self.owner = Profile.objects.create(username="search-owner")
        self.contact = Profile.objects.create(
            username="search-contact",
            first_name="UniqueContributor",
            last_name="Researcher",
        )
        self.target = ResourceBase.objects.create(
            uuid=str(uuid4()),
            title="Target resource",
            abstract="A resource used to test related metadata search.",
            owner=self.owner,
        )
        self.decoy = ResourceBase.objects.create(
            uuid=str(uuid4()),
            title="Decoy resource",
            abstract="A resource that only matches the contributor.",
            owner=self.owner,
        )
        ContactRole.objects.create(resource=self.target, contact=self.contact, role="author")
        ContactRole.objects.create(resource=self.decoy, contact=self.contact, role="author")
        self.target.related_projects.add(
            RelatedProject.objects.create(
                label="unique-project",
                display_name="Unique Project",
                description="Project metadata for search",
            )
        )

    def _search(self, term, fields):
        request = Request(
            RequestFactory().get(
                "/api/v2/resources",
                {"search": term, "search_fields": fields},
            )
        )
        return DynamicSearchFilter().filter_queryset(request, ResourceBase.objects.all(), view=None)

    def test_search_uses_or_across_direct_and_related_fields(self):
        results = self._search(
            "UniqueContributor",
            ["title", "contacts__first_name", "related_projects__display_name"],
        )

        self.assertSetEqual(set(results.values_list("pk", flat=True)), {self.target.pk, self.decoy.pk})

    def test_search_uses_and_across_terms_from_different_relations(self):
        results = self._search(
            '"UniqueContributor" "Unique Project"',
            ["title", "contacts__first_name", "related_projects__display_name"],
        )

        self.assertSetEqual(set(results.values_list("pk", flat=True)), {self.target.pk})

    def test_related_groups_compile_as_independent_exists_clauses(self):
        results = self._search(
            "Unique",
            ["contacts__first_name", "related_projects__display_name"],
        )

        sql = str(results.query).upper()
        self.assertGreaterEqual(sql.count("EXISTS"), 2)
        self.assertNotIn('JOIN "BASE_RELATEDPROJECT"', sql.split("EXISTS", 1)[0])
