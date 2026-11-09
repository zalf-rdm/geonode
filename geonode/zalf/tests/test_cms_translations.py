"""
Tests for the per-language CMS content fields (zalf-rdm/geonode#901).

Highlighted cases, spotlight banners and training resources follow the Topic
pattern: the base field holds the English / default value, `<field>_<lang>`
holds a translation, and a blank translation falls back to the base field. The
API sends the raw variants (the client resolves them against MapStore's live
locale); the server-rendered detail pages resolve them for Django's language.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from geonode.zalf.models import (
    TRANSLATED_LANGUAGES,
    HighlightedCase,
    SpotlightBanner,
    Topic,
    TrainingResource,
    translated_field_names,
)
from geonode.zalf.tests.test_cms_topics import basic_auth


def make_case(**kwargs):
    defaults = {"tab_label": "Soil", "title": "Soil case", "href": "/catalogue/", "body_markdown": "English body"}
    return HighlightedCase.objects.create(**{**defaults, **kwargs})


class TestLocalizedFields(TestCase):
    def test_uses_the_active_language(self):
        case = make_case(title_fr="Cas sol")
        with translation.override("fr"):
            self.assertEqual(case.localized("title"), "Cas sol")

    def test_normalises_the_locale(self):
        case = make_case(title_de="Bodenfall")
        self.assertEqual(case.localized("title", "de-DE"), "Bodenfall")
        self.assertEqual(case.localized("title", "DE"), "Bodenfall")

    def test_falls_back_to_the_base_field(self):
        case = make_case(title_es="   ")
        self.assertEqual(case.localized("title", "es"), "Soil case")
        self.assertEqual(case.localized("title", "en"), "Soil case")
        # A language without a column must not reach some unrelated attribute.
        self.assertEqual(case.localized("title", "xx"), "Soil case")

    def test_every_translated_field_has_all_variants(self):
        for model in (HighlightedCase, SpotlightBanner, TrainingResource, Topic):
            names = {field.name for field in model._meta.get_fields()}
            for name in translated_field_names(*model.TRANSLATED_FIELDS):
                self.assertIn(name, names, f"{model.__name__}.{name}")

    def test_topic_localized_name_still_works(self):
        topic = Topic.objects.create(name="Soil", slug="soil-901", name_fr="Sol")
        self.assertEqual(topic.localized_name("fr"), "Sol")
        self.assertEqual(topic.localized_name("es"), "Soil")


class TestCmsTranslationsApi(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user("i18n-staff", "staff@example.test", "pw", is_staff=True)

    def test_list_endpoints_send_the_raw_variants(self):
        make_case(title_de="Bodenfall")
        SpotlightBanner.objects.create(kicker="New", title="Banner", button_text="Go", href="/", title_es="Pancarta")
        TrainingResource.objects.create(title="Course", organizer="ZALF", category_fr="Sols")
        cases = self.client.get(reverse("cms_cases")).json()
        banners = self.client.get(reverse("cms_banners")).json()
        trainings = self.client.get(reverse("cms_trainings")).json()
        self.assertEqual(cases[0]["title"], "Soil case")
        self.assertEqual(cases[0]["title_de"], "Bodenfall")
        self.assertEqual(banners[0]["title_es"], "Pancarta")
        self.assertEqual(trainings[0]["category_fr"], "Sols")
        for code in TRANSLATED_LANGUAGES:
            self.assertIn(f"eyebrow_{code}", cases[0])
            self.assertIn(f"kicker_{code}", banners[0])
            self.assertIn(f"duration_{code}", trainings[0])

    def test_detail_renders_the_body_for_the_request_language(self):
        case = make_case(body_markdown_de="Deutscher Text")
        url = reverse("cms_case_detail", kwargs={"pk_or_slug": case.slug})
        german = self.client.get(url, HTTP_ACCEPT_LANGUAGE="de").json()
        english = self.client.get(url, HTTP_ACCEPT_LANGUAGE="en").json()
        self.assertIn("Deutscher Text", german["body_html"])
        self.assertIn("English body", english["body_html"])
        self.assertEqual(german["body_markdown_de"], "Deutscher Text")

    def test_write_round_trip(self):
        response = self.client.post(
            reverse("cms_banners"),
            {"kicker": "New", "title": "Banner", "button_text": "Go", "href": "/", "title_fr": "Bannière"},
            **basic_auth("i18n-staff"),
        )
        self.assertEqual(response.status_code, 201, response.content)
        banner = SpotlightBanner.objects.get(pk=response.json()["id"])
        self.assertEqual(banner.title_fr, "Bannière")
        self.assertEqual(banner.title_de, "")


class TestServerRenderedDetailPages(TestCase):
    def test_case_detail_uses_the_translation(self):
        case = make_case(title_fr="Cas sol", body_markdown_fr="Texte français")
        response = self.client.get(reverse("case_detail", kwargs={"slug": case.slug}), HTTP_ACCEPT_LANGUAGE="fr")
        self.assertContains(response, "Cas sol")
        self.assertContains(response, "Texte français")
        self.assertNotContains(response, "English body")

    def test_training_detail_falls_back_to_the_base_fields(self):
        training = TrainingResource.objects.create(title="Course", organizer="ZALF", body_markdown="Course body")
        response = self.client.get(
            reverse("training_detail", kwargs={"slug": training.slug}), HTTP_ACCEPT_LANGUAGE="es"
        )
        self.assertContains(response, "Course")
        self.assertContains(response, "Course body")
