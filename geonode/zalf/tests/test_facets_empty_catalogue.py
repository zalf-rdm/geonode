"""
Regression test for the owner/author facets on an empty catalogue
(zalf-rdm/geonode#863).

`OwnerFacetProvider` and `AuthorFacetProvider` used `queryset or <fallback>`.
A Django queryset is falsy when it is *empty*, so with no visible resources the
`or` substituted a User queryset and the subsequent `.values("owner")` /
`.values("contacts")` raised FieldError — a hard 500 on
`/api/v2/facets/owner` and `/api/v2/facets/author`.

Kept in the fork's own test package rather than appended to
`geonode/facets/tests.py`, so the upstream test module stays untouched.
"""

from django.test import TestCase
from django.urls import reverse

from geonode.base.models import ResourceBase
from geonode.facets.providers.users import AuthorFacetProvider, OwnerFacetProvider


class TestUserFacetsOnEmptyCatalogue(TestCase):
    def test_owner_facet_endpoint_does_not_500(self):
        self.assertFalse(ResourceBase.objects.exists(), "fixture-free test expects an empty catalogue")
        response = self.client.get(reverse("get_facet", args=["owner"]))
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["topics"]["total"], 0)

    def test_author_facet_endpoint_does_not_500(self):
        response = self.client.get(reverse("get_facet", args=["author"]))
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertEqual(response.json()["topics"]["total"], 0)

    def test_providers_handle_an_empty_queryset_directly(self):
        empty = ResourceBase.objects.none()
        self.assertFalse(bool(empty), "an empty queryset must be falsy for this to be a regression test")
        for provider in (OwnerFacetProvider(), AuthorFacetProvider()):
            with self.subTest(provider=provider.name):
                count, items = provider.get_facet_items(empty)
                self.assertEqual(count, 0)
                self.assertEqual(items, [])

    def test_providers_handle_none_without_touching_the_user_model(self):
        # The defensive default must fall back to ResourceBase, not User.
        for provider in (OwnerFacetProvider(), AuthorFacetProvider()):
            with self.subTest(provider=provider.name):
                count, items = provider.get_facet_items(None)
                self.assertEqual(count, 0)
                self.assertEqual(items, [])
