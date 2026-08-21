import ast
from django.test.utils import override_settings
from owslib.etree import etree
from geonode.base.populate_test_data import create_single_doc, create_single_dataset, create_single_map
from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory
from geonode.catalogue.views import csw_global_dispatch
from geonode.base.models import ResourceBase
from django.test import TestCase
from django.conf import settings

pycsw_settings = settings.PYCSW.copy()
pycsw_settings_all = settings.PYCSW.copy()
pycsw_settings["FILTER"] = {"resource_type__in": ["dataset", "map"]}
pycsw_settings_all["FILTER"] = {"resource_type__in": ["dataset", "map", "document"]}


class TestGeoNodeRepository(TestCase):
    # to simplify the tests we pass throught csw_global_dispatch
    # since call the GeoNodeRepository.query
    def setUp(self):
        self.layer = create_single_dataset("dataset_name")
        self.map = create_single_map("map_name")
        self.doc = create_single_doc("doc_name")
        self.request = self.__request_factory()

    def test_if_pycsw_filter_is_not_set_should_return_only_the_dataset_by_default(self):
        response = csw_global_dispatch(self.request)
        root = etree.fromstring(response.content)
        child = [x.attrib for x in root if "numberOfRecordsMatched" in x.attrib]
        returned_results = ast.literal_eval(child[0].get("numberOfRecordsMatched", "0")) if child else 0
        self.assertEqual(1, returned_results)

    @override_settings(PYCSW=pycsw_settings)
    def test_if_pycsw_filter_is_set_should_return_only_datasets_and_map(self):
        response = csw_global_dispatch(self.request)
        root = etree.fromstring(response.content)
        child = [x.attrib for x in root if "numberOfRecordsMatched" in x.attrib]
        returned_results = ast.literal_eval(child[0].get("numberOfRecordsMatched", "0")) if child else 0
        self.assertEqual(2, returned_results)

    @override_settings(PYCSW=pycsw_settings_all)
    def test_if_pycsw_filter_is_set_should_return_all_datasets_map_doc(self):
        response = csw_global_dispatch(self.request)
        root = etree.fromstring(response.content)
        child = [x.attrib for x in root if "numberOfRecordsMatched" in x.attrib]
        returned_results = ast.literal_eval(child[0].get("numberOfRecordsMatched", "0")) if child else 0
        self.assertEqual(3, returned_results)

    def test_unpublished_resources_are_hidden(self):
        """
        Unpublished resources must not be exposed through CSW (#706).

        is_published is flipped after creation rather than passed to the factory
        so the resource still gets the normal default permissions - that isolates
        the repository filter under test from the separate permission mask
        csw_global_dispatch builds from get_objects_for_user().
        """
        unpublished = create_single_dataset("unpublished_dataset_name")
        ResourceBase.objects.filter(pk=unpublished.pk).update(is_published=False)

        # only self.layer; the unpublished dataset is filtered out
        self.assertEqual(1, self.__number_of_records_matched(csw_global_dispatch(self.request)))

    @override_settings(PYCSW=pycsw_settings_all)
    def test_unpublished_resources_are_hidden_with_custom_pycsw_filter(self):
        """
        The exclusion has to survive a deployment-supplied PYCSW["FILTER"], which
        replaces the default wholesale. This is the case that regresses if the
        is_published condition is added to that default instead of to the
        repository-wide mask in GeoNodeRepository._get_repo_filter().
        """
        ResourceBase.objects.filter(pk=self.map.pk).update(is_published=False)

        # dataset + doc would be 3 with the map; the unpublished map drops out
        self.assertEqual(2, self.__number_of_records_matched(csw_global_dispatch(self.request)))

    @staticmethod
    def __number_of_records_matched(response):
        root = etree.fromstring(response.content)
        child = [x.attrib for x in root if "numberOfRecordsMatched" in x.attrib]
        return ast.literal_eval(child[0].get("numberOfRecordsMatched", "0")) if child else 0

    @staticmethod
    def __request_factory():
        factory = RequestFactory()
        url = "http://localhost:8000/catalogue/csw?request=GetRecords"
        url += "&service=CSW&version=2.0.2&outputschema=http%3A%2F%2Fwww.isotc211.org%2F2005%2Fgmd"
        url += "&elementsetname=brief&typenames=csw:Record&resultType=results"
        request = factory.get(url)

        request.user = AnonymousUser()
        return request


class TestExternalCswRedirect(TestCase):
    """
    When CATALOGUE["default"]["ENGINE"] is not pycsw_local, /catalogue/csw
    redirects to the externally deployed CSW. CSW is entirely query-string
    driven, so dropping the query string leaves the remote pycsw with no
    operation to dispatch and the client gets a 404 instead of its capabilities
    document - which is what broke QGIS against the standalone pycsw container
    (#384).
    """

    EXTERNAL = "geonode.catalogue.backends.pycsw_http"

    def setUp(self):
        factory = RequestFactory()
        url = "http://localhost:8000/catalogue/csw?request=GetRecords"
        url += "&service=CSW&version=2.0.2&elementsetname=brief&typenames=csw:Record&resultType=results"
        self.request = factory.get(url)
        self.request.user = AnonymousUser()

    def _dispatch(self, url):
        catalogue = {"default": dict(settings.CATALOGUE["default"])}
        catalogue["default"]["ENGINE"] = self.EXTERNAL
        catalogue["default"]["URL"] = url
        with override_settings(CATALOGUE=catalogue):
            return csw_global_dispatch(self.request)

    def test_query_string_is_forwarded(self):
        response = self._dispatch("http://pycsw:8000/")
        self.assertEqual(302, response.status_code)
        location = response.headers["Location"]
        self.assertTrue(location.startswith("http://pycsw:8000/?"), location)
        self.assertIn("request=GetRecords", location)
        self.assertIn("service=CSW", location)

    def test_query_string_is_merged_with_an_existing_one(self):
        response = self._dispatch("http://pycsw:8000/csw?foo=1")
        self.assertEqual(302, response.status_code)
        location = response.headers["Location"]
        self.assertIn("foo=1", location)
        self.assertIn("request=GetRecords", location)

    def test_url_pointing_back_at_geonode_is_refused(self):
        # CATALOGUE_URL defaults to SITEURL + /catalogue/csw, so switching only
        # CATALOGUE_ENGINE would otherwise redirect to this view forever.
        response = self._dispatch("http://testserver/catalogue/csw")
        self.assertEqual(500, response.status_code)

    def test_relative_url_pointing_back_at_geonode_is_refused(self):
        response = self._dispatch("/catalogue/csw")
        self.assertEqual(500, response.status_code)

    def test_local_backend_still_serves_csw_itself(self):
        # The default engine must keep answering in-process, not redirect.
        response = csw_global_dispatch(self.request)
        self.assertEqual(200, response.status_code)
