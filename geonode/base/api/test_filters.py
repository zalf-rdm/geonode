from uuid import uuid4

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import RequestFactory, TestCase
from rest_framework.request import Request

from geonode.base.api.filters import DynamicSearchFilter, ExtentFilter
from geonode.base.models import ContactRole, GeoKeyword, RelatedProject, ResourceBase
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


class ExtentFilterSpatialTruthTests(TestCase):
    def setUp(self):
        self.owner = Profile.objects.create(username="extent-owner")
        self.germany = self._resource("German field data", (10, 50, 11, 51))
        self.world_fallback = self._resource("Unspecified world extent", (-179.999, -85.06, 179.999, 85.06))
        self.placeholder = self._resource("Placeholder extent", (-1, -1, 0, 0))
        self.gadm_resource = self._resource("Lagoa Grande table", (-1, -1, 0, 0))

        brazil = GeoKeyword.objects.create(
            source="GADM",
            level=0,
            layer_name="gid_0",
            gid="BRA",
            name="Brazil",
            geometry=self._multipolygon((-74, -34, -34, 6)),
        )
        lagoa_grande = GeoKeyword.objects.create(
            source="GADM",
            level=2,
            layer_name="gid_2",
            gid="BRA.17.101_2",
            name="Lagoa Grande",
            geometry=self._multipolygon((-41.2, -9.0, -40.0, -8.0)),
        )
        self.gadm_resource.geo_keywords.add(brazil, lagoa_grande)

    @staticmethod
    def _multipolygon(extent):
        polygon = Polygon.from_bbox(extent)
        polygon.srid = 4326
        return MultiPolygon(polygon, srid=4326)

    def _resource(self, title, extent):
        polygon = Polygon.from_bbox(extent)
        polygon.srid = 4326
        return ResourceBase.objects.create(
            uuid=str(uuid4()),
            title=title,
            owner=self.owner,
            ll_bbox_polygon=polygon,
        )

    def _filter(self, extent):
        request = Request(RequestFactory().get("/api/v2/resources", {"extent": extent}))
        return ExtentFilter().filter_queryset(request, ResourceBase.objects.all(), view=None)

    def test_excludes_global_and_placeholder_fallbacks(self):
        results = self._filter("5,47,16,56")

        self.assertSetEqual(set(results.values_list("pk", flat=True)), {self.germany.pk})

    def test_matches_the_deepest_gadm_boundary(self):
        results = self._filter("-41.1,-8.9,-40.1,-8.1")

        self.assertSetEqual(set(results.values_list("pk", flat=True)), {self.gadm_resource.pk})

    def test_does_not_match_a_broad_gadm_ancestor(self):
        results = self._filter("-36,-9,-35,-8")

        self.assertNotIn(self.gadm_resource.pk, set(results.values_list("pk", flat=True)))
