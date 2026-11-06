"""
Tests for /imprint/, which forwards to the operator's own imprint (#731)
rather than serving a copy maintained in this repository.
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from geonode.zalf.views import zalf_imprint_url

DE = "https://example.org/de/impressum"
EN = "https://example.org/en/imprint"

# The URLs are configurable, so the tests pin their own rather than the
# shipped defaults -- otherwise they would only prove settings.py was read.
URLS = {"ZALF_IMPRINT_URL_DE": DE, "ZALF_IMPRINT_URL_EN": EN}


@override_settings(**URLS)
class TestImprintUrl(TestCase):
    """The language -> URL mapping, independent of the request cycle."""

    def test_german_gets_the_german_imprint(self):
        self.assertEqual(zalf_imprint_url("de"), DE)

    def test_english_gets_the_english_imprint(self):
        self.assertEqual(zalf_imprint_url("en"), EN)

    def test_locale_variants_are_normalised(self):
        for code in ("de-DE", "DE", "de-AT"):
            with self.subTest(code=code):
                self.assertEqual(zalf_imprint_url(code), DE)

    def test_other_site_languages_fall_back_to_english(self):
        """
        The site ships fr/es/it, but the operator publishes the imprint in
        German and English only -- so these must not 404 on zalf.de.
        """
        for code in ("fr", "es", "it", "pt-BR"):
            with self.subTest(code=code):
                self.assertEqual(zalf_imprint_url(code), EN)

    def test_no_active_language_falls_back_to_english(self):
        with translation.override(None):
            self.assertEqual(zalf_imprint_url(), EN)

    def test_follows_the_active_language(self):
        with translation.override("de"):
            self.assertEqual(zalf_imprint_url(), DE)
        with translation.override("en"):
            self.assertEqual(zalf_imprint_url(), EN)


@override_settings(**URLS)
class TestImprintRedirect(TestCase):
    # Not SimpleTestCase: the sites middleware resolves the current Site from
    # the database on every request, so a DB-less case never reaches the view.

    def get(self, **kwargs):
        return self.client.get("/imprint/", SERVER_NAME="localhost", **kwargs)

    def test_forwards_to_the_configured_imprint(self):
        response = self.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], EN)

    def test_a_german_reader_is_sent_to_the_german_imprint(self):
        self.assertEqual(self.get(HTTP_ACCEPT_LANGUAGE="de")["Location"], DE)

    def test_an_english_reader_is_sent_to_the_english_imprint(self):
        self.assertEqual(self.get(HTTP_ACCEPT_LANGUAGE="en")["Location"], EN)

    def test_redirect_is_temporary(self):
        """
        Deliberately 302, not 301. A permanent redirect is cached hard by
        browsers, which would both pin anyone who visited once to the external
        page if a local imprint were ever restored, and freeze the language
        chosen on their first visit.
        """
        self.assertEqual(self.get().status_code, 302)

    def test_the_named_url_still_resolves(self):
        """
        Both footers and the cookie notice link by name, so the name has to
        keep working -- that is what makes one redirect cover every link.
        """
        self.assertEqual(reverse("imprint"), "/imprint/")


class TestShippedDefaults(TestCase):
    """
    Guards the defaults themselves. The tests above override the settings, so
    without this a typo in settings.py would go unnoticed. The two paths are
    deliberately not parallel -- "Seiten" vs "Pages" -- so neither can be
    derived from the other by swapping the language code.
    """

    def test_default_urls_are_the_zalf_imprint(self):
        self.assertEqual(zalf_imprint_url("de"), "https://www.zalf.de/de/ueber_uns/Seiten/impressum.aspx")
        self.assertEqual(zalf_imprint_url("en"), "https://www.zalf.de/en/ueber_uns/Pages/impressum.aspx")
