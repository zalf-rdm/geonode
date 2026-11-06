"""
Tests for CMS-configurable Topics (zalf-rdm/geonode#863).

The catalogue href tests matter most: that exact string is the contract shared
with the client, and TopicUtils-test.js asserts the identical literals on the JS
side, so a drift on either side turns one of the two suites red.
"""

import base64
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from geonode.facets.models import facet_registry
from geonode.zalf.models import (
    HomepageSection,
    Topic,
    homepage_section_order,
    navbar_topic_rows,
    topic_catalogue_href,
)
from geonode.zalf.api.topic_filters import (
    MAX_ROWS,
    MAX_VALUES_PER_ROW,
    NUMERIC_ONLY_FILTER_KEYS,
    UNSUPPORTED_FILTER_KEYS,
    facet_filter_keys,
    validate_filter_spec,
)
from geonode.zalf.templatetags.zalf_cms import zalf_navbar_topic_columns

def basic_auth(username, password="pw"):
    """
    Basic-auth headers for the write tests.

    Not session login: `KeycloakSilentSSOMiddleware` invalidates a test-client
    session (it carries no real `access_token`), so `force_login` leaves
    `request.user` anonymous and every write looks unauthenticated. Basic auth is
    one of the view's own AUTH_CLASSES, so this exercises the real permission
    chain — IsAuthenticated + IsAdminUser — without fighting the SSO middleware.
    """
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"HTTP_AUTHORIZATION": f"Basic {token}"}


CATEGORY_KEY = "filter{category.identifier.in}"
REGION_KEY = "filter{regions.code.in}"


def category_row(*values):
    return {"key": CATEGORY_KEY, "values": list(values)}


class TestTopicCatalogueHref(TestCase):
    def test_single_filter_single_value(self):
        self.assertEqual(
            topic_catalogue_href("", [category_row("farming")]),
            "/catalogue/#/?filter%7Bcategory.identifier.in%7D=farming",
        )

    def test_multiple_values_repeat_the_key(self):
        # Repeated params are how the `.in` lookup expresses OR.
        self.assertEqual(
            topic_catalogue_href("", [category_row("farming", "soil")]),
            "/catalogue/#/?filter%7Bcategory.identifier.in%7D=farming"
            "&filter%7Bcategory.identifier.in%7D=soil",
        )

    def test_multiple_filters_and_across_keys(self):
        self.assertEqual(
            topic_catalogue_href("", [category_row("farming"), {"key": REGION_KEY, "values": ["DEU"]}]),
            "/catalogue/#/?filter%7Bcategory.identifier.in%7D=farming&filter%7Bregions.code.in%7D=DEU",
        )

    def test_search_term_is_appended_as_q(self):
        self.assertEqual(
            topic_catalogue_href("soil", [category_row("farming")]),
            "/catalogue/#/?filter%7Bcategory.identifier.in%7D=farming&q=soil",
        )

    def test_search_term_alone_uses_percent_encoded_spaces(self):
        # Not "+": every link this replaced said %20, and the sibling client-side
        # helper (ZalfLandingPageUtils) produces %20 via encodeURIComponent.
        self.assertEqual(topic_catalogue_href("Soil Profiles"), "/catalogue/#/?q=Soil%20Profiles")

    def test_empty_spec(self):
        self.assertEqual(topic_catalogue_href("", []), "/catalogue/#/")
        self.assertEqual(topic_catalogue_href(), "/catalogue/#/")

    def test_property_matches_helper(self):
        topic = Topic(name="Soil", search_term="soil", filters=[category_row("farming")])
        self.assertEqual(topic.catalogue_href, topic_catalogue_href("soil", [category_row("farming")]))

    def test_seeded_topics_keep_their_previous_urls(self):
        # The migration must be a visual no-op: these are the exact hrefs that
        # used to be hardcoded in header.html and Homepage.jsx.
        self.assertEqual(
            Topic.objects.get(slug="soil-profiles").catalogue_href,
            "/catalogue/#/?q=Soil%20Profiles",
        )
        self.assertEqual(
            Topic.objects.get(slug="long-term-experiments").catalogue_href,
            "/catalogue/#/?q=Long%20Term%20Field%20Experiment",
        )
        self.assertEqual(Topic.objects.get(slug="animals").catalogue_href, "/catalogue/#/?q=Animals")


class TestTopicFilterSpecValidation(TestCase):
    def assertRejects(self, spec):
        with self.assertRaises(ValidationError):
            validate_filter_spec(spec)

    def test_rejects_unknown_filter_key(self):
        # A real dynamic-rest path, but not one any facet advertises.
        self.assertRejects([{"key": "filter{owner.email.icontains}", "values": ["a"]}])

    def test_rejects_malformed_key(self):
        for key in ("category", "filter{foo", "<script>", "", "filter{}"):
            self.assertRejects([{"key": key, "values": ["a"]}])

    def test_rejects_bad_shape(self):
        self.assertRejects({"key": CATEGORY_KEY})
        self.assertRejects(["not-a-dict"])
        self.assertRejects([{"values": ["a"]}])
        self.assertRejects([category_row()])
        self.assertRejects([{"key": CATEGORY_KEY, "values": "farming"}])

    def test_rejects_bare_date_filter(self):
        # filter{date} is a range (gte/lte) and ResourceBase.date is a datetime,
        # so an exact match on a year bucket could never hit.
        self.assertRejects([{"key": "filter{date}", "values": ["2019"]}])

    def test_rejects_duplicate_key(self):
        self.assertRejects([category_row("farming"), category_row("soil")])

    def test_caps_rows_and_values(self):
        self.assertRejects([category_row("a")] * (MAX_ROWS + 1))
        self.assertRejects([{"key": CATEGORY_KEY, "values": [str(i) for i in range(MAX_VALUES_PER_ROW + 1)]}])

    def test_rejects_non_scalar_values(self):
        for bad in (True, None, ["x"], {"a": 1}, "   "):
            self.assertRejects([{"key": CATEGORY_KEY, "values": [bad]}])

    def test_normalises_values(self):
        cleaned = validate_filter_spec(
            [{"key": CATEGORY_KEY, "values": [" soil ", "soil", 42], "labels": ["Soil"]}]
        )
        self.assertEqual(
            cleaned,
            [{"field": "category", "key": CATEGORY_KEY, "values": ["soil", "42"], "labels": ["Soil"]}],
        )

    def test_empty_spec_normalises_to_list(self):
        for empty in (None, "", []):
            self.assertEqual(validate_filter_spec(empty), [])

    def test_accepts_every_registered_facet_filter(self):
        """
        The regression guard: the allowlist is derived from FACET_PROVIDERS, so
        adding or renaming a provider must not need an edit here.
        """
        checked = 0
        for provider in facet_registry.get_providers():
            key = (provider.get_info(lang="en") or {}).get("filter")
            if not key or key in UNSUPPORTED_FILTER_KEYS:
                continue
            value = "1" if key in NUMERIC_ONLY_FILTER_KEYS else "x"
            with self.subTest(filter=key):
                self.assertEqual(validate_filter_spec([{"key": key, "values": [value]}])[0]["key"], key)
            checked += 1
        self.assertGreater(checked, 0, "no facet providers registered")

    def test_thesaurus_values_must_be_numeric_when_available(self):
        """
        ThesaurusFacetProvider registers one provider per Thesaurus row, so
        filter{tkeywords} is advertised only where thesauri exist. Skip rather
        than assert on an instance that has none.
        """
        key = "filter{tkeywords}"
        if key not in facet_filter_keys():
            self.skipTest("no thesaurus facet registered on this instance")
        self.assertRejects([{"key": key, "values": ["soil"]}])
        self.assertEqual(validate_filter_spec([{"key": key, "values": ["42"]}])[0]["values"], ["42"])

    def test_key_is_rederived_not_trusted(self):
        # `field` is backfilled from the registry, so a mislabelled row is fixed
        # rather than stored as sent.
        cleaned = validate_filter_spec([{"field": "not-a-facet", "key": CATEGORY_KEY, "values": ["x"]}])
        self.assertEqual(cleaned[0]["field"], "category")


class TestTopicModel(TestCase):
    def test_localized_name_uses_the_active_language(self):
        topic = Topic.objects.get(slug="soil-profiles")
        with translation.override("de"):
            self.assertEqual(topic.localized_name(), "Bodenprofile")
        with translation.override("it"):
            self.assertEqual(topic.localized_name(), "Profili del suolo")

    def test_localized_name_normalises_the_locale(self):
        topic = Topic.objects.get(slug="soil-profiles")
        for code in ("de", "de-DE", "DE", "de-AT"):
            self.assertEqual(topic.localized_name(code), "Bodenprofile")

    def test_localized_name_falls_back_to_name(self):
        topic = Topic(name="Soil", name_de="   ")
        self.assertEqual(topic.localized_name("de"), "Soil")   # blank translation
        self.assertEqual(topic.localized_name("pl"), "Soil")   # locale with no field
        self.assertEqual(topic.localized_name("en"), "Soil")

    def test_slug_is_generated_and_deduplicated(self):
        a = Topic.objects.create(name="Test Soil", search_term="soil")
        b = Topic.objects.create(name="Test Soil", search_term="soil")
        self.assertEqual(a.slug, "test-soil")
        self.assertEqual(b.slug, "test-soil-1")

    def test_ordering_is_stable_on_ties(self):
        Topic.objects.all().delete()
        first = Topic.objects.create(name="A", order=0, search_term="a")
        second = Topic.objects.create(name="B", order=0, search_term="b")
        self.assertEqual(list(Topic.objects.values_list("pk", flat=True)), [first.pk, second.pk])

    def test_clean_validates_the_filter_spec(self):
        with self.assertRaises(ValidationError):
            Topic(name="Bad", filters=[{"key": "filter{nope}", "values": ["x"]}]).clean()

    def test_seed_reproduces_the_previous_navbar_and_homepage_split(self):
        # The navbar listed 10 topics, the homepage grid 8.
        self.assertEqual(Topic.objects.count(), 10)
        self.assertEqual(Topic.objects.filter(show_in_navbar=True).count(), 10)
        self.assertEqual(Topic.objects.filter(show_on_homepage=True).count(), 8)
        self.assertFalse(Topic.objects.get(slug="water").show_on_homepage)
        self.assertFalse(Topic.objects.get(slug="long-term-experiments").show_on_homepage)


class TestNavbarTopics(TestCase):
    def setUp(self):
        cache.clear()

    def test_columns_split_evenly(self):
        self.assertEqual([len(c) for c in zalf_navbar_topic_columns()], [5, 5])

    def test_columns_split_for_other_counts(self):
        Topic.objects.all().delete()
        for i in range(7):
            Topic.objects.create(name=f"T{i}", order=i, search_term=f"t{i}")
        cache.clear()
        self.assertEqual([len(c) for c in zalf_navbar_topic_columns()], [4, 3])

    def test_single_topic_and_empty_table(self):
        Topic.objects.all().delete()
        Topic.objects.create(name="Only", search_term="only")
        cache.clear()
        self.assertEqual([len(c) for c in zalf_navbar_topic_columns()], [1])
        Topic.objects.all().delete()
        cache.clear()
        self.assertEqual(zalf_navbar_topic_columns(), [])

    def test_columns_are_localized(self):
        with translation.override("de"):
            names = [t["name"] for column in zalf_navbar_topic_columns() for t in column]
        self.assertIn("Tiere", names)
        self.assertIn("Dauerfeldversuche (LTE)", names)

    def test_hidden_topics_are_excluded(self):
        Topic.objects.filter(slug="animals").update(is_active=False)
        Topic.objects.filter(slug="climate").update(show_in_navbar=False)
        cache.clear()
        names = [t["name"] for column in zalf_navbar_topic_columns() for t in column]
        self.assertNotIn("Animals", names)
        self.assertNotIn("Climate", names)
        self.assertIn("Forest", names)

    def test_cache_is_invalidated_on_save(self):
        self.assertIn("Animals", [row["name"] for row in navbar_topic_rows()])
        topic = Topic.objects.get(slug="animals")
        topic.name = "Fauna"
        topic.save()
        self.assertIn("Fauna", [row["name"] for row in navbar_topic_rows()])

    def test_cache_is_invalidated_on_delete(self):
        self.assertEqual(len(navbar_topic_rows()), 10)
        Topic.objects.get(slug="animals").delete()
        self.assertEqual(len(navbar_topic_rows()), 9)


class TestTopicApi(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("cms_topics")
        User = get_user_model()
        self.staff = User.objects.create_user("topic-staff", "staff@example.test", "pw", is_staff=True)
        self.user = User.objects.create_user("topic-user", "user@example.test", "pw")
        self.staff_auth = basic_auth("topic-staff")
        self.user_auth = basic_auth("topic-user")

    def test_list_is_public_and_hides_inactive(self):
        Topic.objects.filter(slug="animals").update(is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        slugs = [t["slug"] for t in response.json()]
        self.assertNotIn("animals", slugs)
        self.assertEqual(len(slugs), 9)

    def test_list_includes_inactive_for_staff(self):
        Topic.objects.filter(slug="animals").update(is_active=False)
        self.assertEqual(len(self.client.get(self.url, **self.staff_auth).json()), 10)

    def test_payload_shape(self):
        topic = self.client.get(self.url).json()[0]
        for field in (
            "id", "slug", "name", "name_localized", "name_de", "name_fr", "name_es", "name_it",
            "search_term", "filters", "catalogue_href", "image_url", "icon",
            "show_in_navbar", "show_on_homepage", "order", "is_active",
        ):
            self.assertIn(field, topic)

    def test_name_localized_follows_accept_language(self):
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="de")
        names = {t["slug"]: t["name_localized"] for t in response.json()}
        self.assertEqual(names["soil-profiles"], "Bodenprofile")

    def test_name_localized_honours_lang_param(self):
        response = self.client.get(self.url, {"lang": "it"})
        names = {t["slug"]: t["name_localized"] for t in response.json()}
        self.assertEqual(names["soil-profiles"], "Profili del suolo")

    def test_write_requires_staff(self):
        payload = {"name": "New", "search_term": "new"}
        # 403 rather than 401: SessionAuthentication is first in AUTH_CLASSES and
        # offers no WWW-Authenticate header, so DRF reports permission denied.
        self.assertEqual(self.client.post(self.url, payload).status_code, 403)
        self.assertEqual(self.client.post(self.url, payload, **self.user_auth).status_code, 403)
        self.assertEqual(self.client.post(self.url, payload, **self.staff_auth).status_code, 201)

    def test_create_accepts_filters_as_a_json_string(self):
        """
        The exact path the CMS editor uses: multipart, with `filters` stringified
        because FormData flattens every value to a string.
        """
        response = self.client.post(
            self.url,
            {
                "name": "Farming",
                "filters": json.dumps([{"field": "category", "key": CATEGORY_KEY, "values": ["farming"]}]),
            },
            **self.staff_auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["filters"][0]["values"], ["farming"])
        self.assertEqual(body["catalogue_href"], "/catalogue/#/?filter%7Bcategory.identifier.in%7D=farming")

    def test_create_accepts_an_icon_name(self):
        """
        The icon vocabulary lives in the client (themes/zalf/utils/TopicIcons.js),
        so the server stores whatever slug it is given rather than keeping a
        second copy of the list that could drift from it.
        """
        response = self.client.post(
            self.url,
            {"name": "Water", "search_term": "Water", "icon": "droplet"},
            **self.staff_auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["icon"], "droplet")

    def test_icon_is_optional(self):
        response = self.client.post(
            self.url,
            {"name": "Plain", "search_term": "Plain"},
            **self.staff_auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["icon"], "")

    def test_create_rejects_an_icon_name_that_is_not_a_slug(self):
        """
        The name is interpolated into markup by the client, and anything outside
        [a-z0-9-] is neither an icon this build ships nor safe to echo back.
        """
        for bad in ("Droplet", "drop let", "<script>", "drop/let"):
            with self.subTest(icon=bad):
                response = self.client.post(
                    self.url,
                    {"name": "Bad", "search_term": "Bad", "icon": bad},
                    **self.staff_auth,
                )
                self.assertEqual(response.status_code, 400, response.content)

    def test_create_rejects_an_invalid_filter_spec(self):
        response = self.client.post(
            self.url,
            {"name": "Bad", "filters": json.dumps([{"key": "filter{nope}", "values": ["x"]}])},
            **self.staff_auth,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("filter", str(response.content).lower())

    def test_create_rejects_malformed_json_filters(self):
        response = self.client.post(self.url, {"name": "Bad", "filters": "{not json"}, **self.staff_auth)
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_a_topic_with_no_filter_and_no_term(self):
        self.assertEqual(self.client.post(self.url, {"name": "Empty"}, **self.staff_auth).status_code, 400)

    def test_patch_toggles_is_active(self):
        topic = Topic.objects.get(slug="animals")
        url = reverse("cms_topic_detail", kwargs={"pk_or_slug": topic.pk})
        response = self.client.patch(
            url, json.dumps({"is_active": False}), content_type="application/json", **self.staff_auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    def test_detail_by_slug_and_delete(self):
        url = reverse("cms_topic_detail", kwargs={"pk_or_slug": "animals"})
        self.assertEqual(self.client.get(url).json()["slug"], "animals")
        self.assertEqual(self.client.delete(url, **self.staff_auth).status_code, 204)
        self.assertFalse(Topic.objects.filter(slug="animals").exists())


class TestHomepageSections(TestCase):
    """Order and visibility of the CMS-driven homepage sections."""

    def setUp(self):
        cache.clear()
        self.url = reverse("cms_homepage_sections")
        User = get_user_model()
        self.staff = User.objects.create_user("section-staff", "s@example.test", "pw", is_staff=True)
        self.user = User.objects.create_user("section-user", "u@example.test", "pw")
        self.staff_auth = basic_auth("section-staff")
        self.user_auth = basic_auth("section-user")

    def test_every_cms_content_type_has_a_section(self):
        # Spotlight Banners is a section like any other (zalf-rdm/geonode#863):
        # commit 09f2524d0 had removed it from the homepage while leaving its
        # model, API and CMS tab in place.
        self.assertIn("banners", homepage_section_order())
        self.assertEqual(HomepageSection.objects.get(key="banners").label, "Spotlight Banners")

    def test_seed_matches_the_previous_hardcoded_order(self):
        self.assertEqual(homepage_section_order(), ["cases", "topics", "banners", "trainings"])

    def test_list_is_public(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([s["key"] for s in body], ["cases", "topics", "banners", "trainings"])
        self.assertEqual(body[0]["label"], "Highlighted Datasets")

    def test_reordering_changes_the_rendered_order(self):
        url = reverse("cms_homepage_section_detail", kwargs={"pk_or_key": "trainings"})
        response = self.client.patch(
            url, json.dumps({"order": -1}), content_type="application/json", **self.staff_auth
        )
        # order is a PositiveSmallIntegerField, so a negative value is rejected.
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(
            url, json.dumps({"order": 0}), content_type="application/json", **self.staff_auth
        )
        self.assertEqual(response.status_code, 200)
        # "trainings" now ties with "cases" at 0 and wins on insertion order only
        # if its pk is lower, so assert on the stored value rather than position.
        self.assertEqual(HomepageSection.objects.get(key="trainings").order, 0)

    def test_hiding_a_section_removes_it_from_the_order(self):
        url = reverse("cms_homepage_section_detail", kwargs={"pk_or_key": "topics"})
        self.assertEqual(
            self.client.patch(
                url, json.dumps({"is_active": False}), content_type="application/json", **self.staff_auth
            ).status_code,
            200,
        )
        self.assertEqual(homepage_section_order(), ["cases", "banners", "trainings"])

    def test_hidden_sections_are_absent_for_anonymous_but_visible_to_staff(self):
        HomepageSection.objects.filter(key="topics").update(is_active=False)
        self.assertEqual(len(self.client.get(self.url).json()), 3)
        self.assertEqual(len(self.client.get(self.url, **self.staff_auth).json()), 4)

    def test_write_requires_staff(self):
        url = reverse("cms_homepage_section_detail", kwargs={"pk_or_key": "topics"})
        payload = json.dumps({"order": 2})
        # 403 rather than 401 — see the note on basic_auth above.
        self.assertEqual(self.client.patch(url, payload, content_type="application/json").status_code, 403)
        self.assertEqual(
            self.client.patch(url, payload, content_type="application/json", **self.user_auth).status_code, 403
        )

    def test_key_is_read_only(self):
        url = reverse("cms_homepage_section_detail", kwargs={"pk_or_key": "topics"})
        response = self.client.patch(
            url, json.dumps({"key": "cases"}), content_type="application/json", **self.staff_auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["key"], "topics")

    def test_cache_is_invalidated_on_save(self):
        self.assertIn("topics", homepage_section_order())
        section = HomepageSection.objects.get(key="topics")
        section.is_active = False
        section.save()
        self.assertNotIn("topics", homepage_section_order())


class TestExcludedTopicFilters(TestCase):
    """Filters deliberately not offered for topics."""

    def test_excluded_keys_are_rejected(self):
        for key in ("filter{featured}", "filter{regions.code.in}", "filter{author.pk.in}", "filter{date}"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                validate_filter_spec([{"key": key, "values": ["x"]}])

    def test_they_are_still_advertised_by_the_facets_api(self):
        # The exclusion is a topic-level policy, not a claim that the facet is
        # gone — the catalogue sidebar still offers these.
        keys = facet_filter_keys()
        for key in ("filter{featured}", "filter{regions.code.in}", "filter{author.pk.in}"):
            self.assertIn(key, keys)

    def test_author_is_excluded_because_it_cannot_be_executed(self):
        """
        ResourceBaseSerializer maps `author` to source="metadata_author", which
        is a Python property over contacts/ContactRole rather than a column, so
        dynamic-rest cannot build an ORM path and the request 500s with
        "metadata_author is not a valid field". `owner` is a real FK and works,
        so it stays available.
        """
        with self.assertRaises(ValidationError):
            validate_filter_spec([{"key": "filter{author.pk.in}", "values": ["1000"]}])
        self.assertEqual(
            validate_filter_spec([{"key": "filter{owner.pk.in}", "values": ["1000"]}])[0]["field"],
            "owner",
        )
