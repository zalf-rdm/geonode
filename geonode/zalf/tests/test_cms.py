from django.test import SimpleTestCase

from geonode.zalf.api.cms_utils import render_markdown


class TestCmsMarkdownSanitization(SimpleTestCase):
    def test_removes_script_and_event_handlers(self):
        html = render_markdown('<script>alert(1)</script><img src="https://example.test/a.png" onerror="alert(1)">')

        self.assertNotIn('<script', html)
        self.assertNotIn('onerror=', html)
        self.assertIn('https://example.test/a.png', html)

    def test_removes_javascript_links_but_keeps_https_links(self):
        html = render_markdown('[unsafe](javascript:alert(1)) [safe](https://example.test/page)')

        self.assertNotIn('javascript:', html)
        self.assertIn('https://example.test/page', html)
