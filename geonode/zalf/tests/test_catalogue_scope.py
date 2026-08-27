"""Unit tests for the ZALF ISO scope codes (issue #707).

Covers the three surfaces the scope code has to reach consistently:
the ``csw_type`` column, the stored ISO XML, and the CSW response itself.
"""

import ast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.test.client import RequestFactory
from owslib.etree import etree

from django.conf import settings

from geonode.base.models import ResourceBase
from geonode.base.populate_test_data import create_single_dataset, create_single_map
from geonode.catalogue.views import csw_global_dispatch
from geonode.maps.models import MapLayer
from geonode.zalf.catalogue import (
    ISO_SCOPE_DATASET,
    ISO_SCOPE_NON_GEOGRAPHIC,
    ISO_SCOPE_SERIES,
    iso_scope_code,
    series_members,
)

GMD = "http://www.isotc211.org/2005/gmd"
GCO = "http://www.isotc211.org/2005/gco"
NSMAP = {"gmd": GMD, "gco": GCO}

# The template under test is ZALF's, not the upstream default.
ZALF_TEMPLATE_SETTINGS = {"CATALOG_METADATA_TEMPLATE": "catalogue/zalf_metadata.xml"}


def make_dataset(name, subtype="vector"):
    """create_single_dataset hardcodes subtype="vector" in its defaults, so it cannot be
    passed as a kwarg; set it afterwards and save so the catalogue signals see it."""
    dataset = create_single_dataset(name)
    if dataset.subtype != subtype:
        dataset.subtype = subtype
        dataset.save()
    return dataset


def parsed_metadata(resource):
    """Return the stored ISO XML of a resource, re-read from the DB, as an lxml tree."""
    xml = ResourceBase.objects.get(pk=resource.pk).metadata_xml
    return etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)


def scope_codes(tree):
    """All MD_ScopeCode values in document order (hierarchyLevel first, then DQ_Scope)."""
    return [el.get("codeListValue") for el in tree.iterfind(f".//{{{GMD}}}MD_ScopeCode")]


class IsoScopeCodeTest(TestCase):
    """The pure mapping, without any template or signal involvement."""

    def test_map_is_a_series(self):
        self.assertEqual(ISO_SCOPE_SERIES, iso_scope_code(create_single_map("scope_map")))

    def test_tabular_dataset_is_non_geographic(self):
        dataset = make_dataset("scope_tabular", subtype="tabular")
        self.assertEqual(ISO_SCOPE_NON_GEOGRAPHIC, iso_scope_code(dataset))

    def test_vector_dataset_stays_a_dataset(self):
        dataset = make_dataset("scope_vector", subtype="vector")
        self.assertEqual(ISO_SCOPE_DATASET, iso_scope_code(dataset))

    def test_tabular_collection_map_is_still_a_series(self):
        """The ZALF-specific 'tabular-collection' subtype must not defeat the map rule."""
        map_obj = create_single_map("scope_tabular_collection", subtype="tabular-collection")
        self.assertEqual(ISO_SCOPE_SERIES, iso_scope_code(map_obj))


class CswTypeColumnTest(TestCase):
    """csw_type backs dc:type and the apiso:Type queryable, so it must track the scope."""

    def test_map_save_sets_csw_type_to_series(self):
        map_obj = create_single_map("csw_type_map")
        self.assertEqual(ISO_SCOPE_SERIES, ResourceBase.objects.get(pk=map_obj.pk).csw_type)

    def test_tabular_dataset_save_sets_csw_type(self):
        dataset = make_dataset("csw_type_tabular", subtype="tabular")
        self.assertEqual(ISO_SCOPE_NON_GEOGRAPHIC, ResourceBase.objects.get(pk=dataset.pk).csw_type)

    def test_vector_dataset_save_keeps_dataset(self):
        dataset = make_dataset("csw_type_vector", subtype="vector")
        self.assertEqual(ISO_SCOPE_DATASET, ResourceBase.objects.get(pk=dataset.pk).csw_type)


@override_settings(**ZALF_TEMPLATE_SETTINGS)
class IsoXmlScopeTest(TestCase):
    """The stored XML is what pycsw dumps verbatim for full ISO records."""

    def test_tabular_dataset_xml_uses_non_geographic_scope(self):
        dataset = make_dataset("xml_tabular", subtype="tabular")
        dataset.save()

        codes = scope_codes(parsed_metadata(dataset))
        self.assertTrue(codes, "expected at least one MD_ScopeCode in the generated XML")
        # Both the hierarchyLevel and the DQ_Scope level must agree.
        self.assertEqual({ISO_SCOPE_NON_GEOGRAPHIC}, set(codes))

    def test_vector_dataset_xml_uses_dataset_scope(self):
        dataset = make_dataset("xml_vector", subtype="vector")
        dataset.save()

        self.assertEqual({ISO_SCOPE_DATASET}, set(scope_codes(parsed_metadata(dataset))))

    def test_map_xml_uses_series_scope(self):
        map_obj = create_single_map("xml_map")
        map_obj.save()

        self.assertEqual({ISO_SCOPE_SERIES}, set(scope_codes(parsed_metadata(map_obj))))

    def test_non_geographic_dataset_has_no_bounding_box(self):
        """A world bbox on a table would claim worldwide coverage; it must be omitted."""
        dataset = make_dataset("xml_tabular_bbox", subtype="tabular")
        dataset.save()

        tree = parsed_metadata(dataset)
        self.assertIsNone(tree.find(f".//{{{GMD}}}EX_GeographicBoundingBox"))

    def test_geographic_dataset_keeps_its_bounding_box(self):
        dataset = make_dataset("xml_vector_bbox", subtype="vector")
        dataset.save()

        tree = parsed_metadata(dataset)
        self.assertIsNotNone(tree.find(f".//{{{GMD}}}EX_GeographicBoundingBox"))


@override_settings(**ZALF_TEMPLATE_SETTINGS)
class SeriesMembersTest(TestCase):
    """The series record lists its members; member records stay untouched."""

    def setUp(self):
        self.dataset = make_dataset("series_member", subtype="vector")
        self.map = create_single_map("series_map")
        MapLayer.objects.create(
            map=self.map,
            dataset=self.dataset,
            name=self.dataset.alternate,
            order=0,
        )

    def aggregate_uuids(self, resource):
        tree = parsed_metadata(resource)
        return [
            el.text.strip()
            for el in tree.iterfind(
                f".//{{{GMD}}}aggregationInfo/{{{GMD}}}MD_AggregateInformation"
                f"/{{{GMD}}}aggregateDataSetIdentifier/{{{GMD}}}MD_Identifier"
                f"/{{{GMD}}}code/{{{GCO}}}CharacterString"
            )
        ]

    def test_series_members_resolves_the_datasets(self):
        self.assertEqual([(self.dataset.uuid, self.dataset.title)], series_members(self.map))

    def test_map_without_layers_has_no_members(self):
        self.assertEqual([], series_members(create_single_map("series_empty_map")))

    def test_a_dataset_has_no_members(self):
        self.assertEqual([], series_members(self.dataset))

    def test_unpublished_member_is_not_listed(self):
        ResourceBase.objects.filter(pk=self.dataset.pk).update(is_published=False)
        self.assertEqual([], series_members(self.map))

    def test_series_xml_lists_its_members(self):
        self.map.save()
        self.assertEqual([self.dataset.uuid], self.aggregate_uuids(self.map))

    def test_member_xml_carries_no_parent_identifier(self):
        """The child side must stay clean -- this is the whole point of the inversion."""
        self.dataset.save()

        tree = parsed_metadata(self.dataset)
        self.assertIsNone(tree.find(f"{{{GMD}}}parentIdentifier"))
        self.assertEqual([], self.aggregate_uuids(self.dataset))

    def test_aggregation_info_precedes_spatial_representation_type(self):
        """AbstractMD_Identification orders resourceConstraints -> aggregationInfo,
        and MD_DataIdentification's own elements come after all of those."""
        self.map.save()

        ident = parsed_metadata(self.map).find(f"{{{GMD}}}identificationInfo/{{{GMD}}}MD_DataIdentification")
        children = [el.tag for el in ident]
        self.assertIn(f"{{{GMD}}}aggregationInfo", children)
        for later in (f"{{{GMD}}}language", f"{{{GMD}}}extent"):
            self.assertLess(children.index(f"{{{GMD}}}aggregationInfo"), children.index(later))

    def test_saving_a_member_refreshes_the_series(self):
        """The map's record embeds member uuids, so members must push updates upward."""
        ResourceBase.objects.filter(pk=self.map.pk).update(metadata_xml="<gmd:MD_Metadata/>")

        self.dataset.save()

        self.assertEqual([self.dataset.uuid], self.aggregate_uuids(self.map))

    def test_deleting_a_member_drops_it_from_the_series(self):
        self.map.save()
        self.assertEqual([self.dataset.uuid], self.aggregate_uuids(self.map))

        self.dataset.delete()

        self.assertEqual([], self.aggregate_uuids(self.map))


class CswExposureTest(TestCase):
    """Maps have to actually reach the CSW, not just carry the right scope code."""

    def setUp(self):
        self.dataset = make_dataset("csw_exposure_dataset", subtype="vector")
        self.map = create_single_map("csw_exposure_map")

        request = RequestFactory().get(
            "/catalogue/csw",
            {
                "service": "CSW",
                "version": "2.0.2",
                "request": "GetRecords",
                "typenames": "csw:Record",
                "elementsetname": "brief",
                "resulttype": "results",
            },
        )
        request.user = AnonymousUser()
        self.request = request

    def _records_matched(self):
        response = csw_global_dispatch(self.request)
        root = etree.fromstring(response.content)
        matched = [x.attrib for x in root if "numberOfRecordsMatched" in x.attrib]
        return ast.literal_eval(matched[0].get("numberOfRecordsMatched", "0")) if matched else 0

    def test_default_filter_exposes_datasets_and_maps(self):
        self.assertEqual({"resource_type__in": ["dataset", "map"]}, settings.PYCSW["FILTER"])
        self.assertEqual(2, self._records_matched())

    def test_dublin_core_full_records_serialize(self):
        """QGIS asks for outputSchema=csw/2.0.2 with elementsetname=full.

        That path builds the record from the queryable columns instead of dumping the
        stored ISO XML, so it breaks on any queryable that resolves to a non-string.
        A map with a publisher is what first tripped it (see TestPublisherCsv).
        """
        self.map.publisher = get_user_model().objects.get(username="admin")

        request = RequestFactory().post(
            "/catalogue/csw",
            data=(
                '<csw:GetRecords xmlns:csw="http://www.opengis.net/cat/csw/2.0.2" '
                'outputSchema="http://www.opengis.net/cat/csw/2.0.2" version="2.0.2" '
                'service="CSW" resultType="results" startPosition="1" maxRecords="25">'
                '<csw:Query typeNames="csw:Record">'
                "<csw:ElementSetName>full</csw:ElementSetName>"
                "</csw:Query></csw:GetRecords>"
            ),
            content_type="application/xml",
        )
        request.user = AnonymousUser()

        root = etree.fromstring(csw_global_dispatch(request).content)

        fault = root.find(".//{http://www.opengis.net/ows}ExceptionText")
        self.assertIsNone(fault, f"CSW returned an exception report: {fault is not None and fault.text}")

        types = {
            rec.findtext("{http://purl.org/dc/elements/1.1/}type")
            for rec in root.iter("{http://www.opengis.net/cat/csw/2.0.2}Record")
        }
        self.assertEqual({ISO_SCOPE_DATASET, ISO_SCOPE_SERIES}, types)


@override_settings(**ZALF_TEMPLATE_SETTINGS)
class SyncCswScopeCommandTest(TestCase):
    """The backfill command has to repair resources that predate the scope codes."""

    STALE_XML = '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"/>'

    def setUp(self):
        self.dataset = make_dataset("command_tabular", subtype="tabular")
        self.map = create_single_map("command_map")
        self._make_stale(self.dataset)
        self._make_stale(self.map)

    def _make_stale(self, resource):
        """Put a resource back into its pre-#707 state, bypassing the signals."""
        ResourceBase.objects.filter(pk=resource.pk).update(
            csw_type=ISO_SCOPE_DATASET,
            metadata_xml=self.STALE_XML,
        )

    def test_command_repairs_csw_type_and_xml(self):
        call_command("zalf_sync_csw_scope", verbosity=0)

        dataset = ResourceBase.objects.get(pk=self.dataset.pk)
        self.assertEqual(ISO_SCOPE_NON_GEOGRAPHIC, dataset.csw_type)
        self.assertEqual({ISO_SCOPE_NON_GEOGRAPHIC}, set(scope_codes(parsed_metadata(self.dataset))))

        map_record = ResourceBase.objects.get(pk=self.map.pk)
        self.assertEqual(ISO_SCOPE_SERIES, map_record.csw_type)
        self.assertEqual({ISO_SCOPE_SERIES}, set(scope_codes(parsed_metadata(self.map))))

    def test_dry_run_changes_nothing(self):
        call_command("zalf_sync_csw_scope", "--dry-run", verbosity=0)

        for resource in (self.dataset, self.map):
            record = ResourceBase.objects.get(pk=resource.pk)
            self.assertEqual(ISO_SCOPE_DATASET, record.csw_type)
            self.assertEqual(self.STALE_XML, record.metadata_xml)

    def test_type_filter_limits_what_is_touched(self):
        call_command("zalf_sync_csw_scope", "--type", "map", verbosity=0)

        self.assertEqual(ISO_SCOPE_SERIES, ResourceBase.objects.get(pk=self.map.pk).csw_type)
        # the dataset was out of scope for this run and must be untouched
        self.assertEqual(ISO_SCOPE_DATASET, ResourceBase.objects.get(pk=self.dataset.pk).csw_type)

    def test_custom_uploaded_xml_is_preserved(self):
        """Same guard as upstream regenerate_xml: never clobber user-supplied XML."""
        custom = '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">custom</gmd:MD_Metadata>'
        ResourceBase.objects.filter(pk=self.dataset.pk).update(
            metadata_uploaded=True,
            metadata_uploaded_preserve=True,
            metadata_xml=custom,
        )

        call_command("zalf_sync_csw_scope", verbosity=0)

        self.assertEqual(custom, ResourceBase.objects.get(pk=self.dataset.pk).metadata_xml)
