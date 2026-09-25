"""
Unit tests for the attribute table in the ZALF metadata handler
(geonode.metadata.handlers.zalf, field "attribute_set").

GeoNode 5 dropped the attribute table of the 4.x metadata form. The ZALF handler brings
it back to the metadata editor: labels, descriptions, units, methods, display order,
visibility and feature info type of a dataset's attributes (zalf-rdm/geonode#745).
"""

from django.test import TestCase

from geonode.base.models import ResourceBase
from geonode.base.populate_test_data import create_single_dataset, create_single_map
from geonode.layers.models import Attribute
from geonode.metadata.exceptions import UnsetFieldException
from geonode.metadata.handlers.zalf import ZalfHandler

FIELD = "attribute_set"


class ZalfAttributeTableTests(TestCase):
    def setUp(self):
        self.handler = ZalfHandler()
        self.dataset = create_single_dataset("zalf_attribute_table")
        self.dataset.attribute_set.all().delete()
        self.density = Attribute.objects.create(
            dataset=self.dataset, attribute="soil_density", attribute_type="xsd:double", display_order=2
        )
        self.depth = Attribute.objects.create(
            dataset=self.dataset,
            attribute="depth",
            attribute_type="xsd:int",
            display_order=1,
            attribute_label="Depth",
        )

    def _update(self, resource, rows):
        errors = {}
        self.handler.update_resource(resource, FIELD, {FIELD: rows}, {}, errors)
        return errors

    # -- schema ------------------------------------------------------------

    def test_schema_describes_a_fixed_attribute_table(self):
        schema = self.handler.update_schema({"properties": {}}, {}, None)
        subschema = schema["properties"][FIELD]

        self.assertEqual(subschema["geonode:handler"], "zalf")
        options = subschema["ui:options"]
        self.assertFalse(options["addable"])
        self.assertFalse(options["removable"])
        self.assertFalse(options["orderable"])
        self.assertFalse(options["label"])  # the "Attributes" group heading already names the section
        self.assertTrue(options["geonode-ui:hideIfEmpty"])

        columns = subschema["items"]["properties"]
        self.assertEqual(columns["attribute"]["title"], "Name")
        for readonly in ("pk", "attribute", "attribute_type"):
            self.assertTrue(columns[readonly]["readOnly"], readonly)
        # not offered in the editor, but still delivered and stored unchanged
        for hidden in ("pk", "display_order", "visible"):
            self.assertEqual(columns[hidden]["ui:widget"], "hidden", hidden)
        for shown in ("attribute_label", "description", "attribute_unit", "attribute_method", "featureinfo_type"):
            self.assertNotIn("ui:widget", columns[shown], shown)
        types = [choice["const"] for choice in columns["featureinfo_type"]["oneOf"]]
        self.assertEqual(types, [value for value, _label in Attribute.TYPES])

    # -- read --------------------------------------------------------------

    def test_instance_lists_attributes_in_display_order(self):
        resource = ResourceBase.objects.get(pk=self.dataset.pk)  # the API passes a plain ResourceBase
        rows = self.handler.get_jsonschema_instance(resource, FIELD, {}, {})

        self.assertEqual([row["attribute"] for row in rows], ["depth", "soil_density"])
        self.assertEqual(rows[0]["pk"], self.depth.pk)
        self.assertEqual(rows[0]["attribute_label"], "Depth")
        self.assertEqual(rows[1]["attribute_label"], "")
        self.assertEqual(rows[1]["attribute_type"], "xsd:double")
        self.assertTrue(rows[1]["visible"])
        self.assertEqual(rows[1]["featureinfo_type"], Attribute.TYPE_PROPERTY)

    def test_instance_is_unset_for_resources_without_attributes(self):
        map_resource = ResourceBase.objects.get(pk=create_single_map("zalf_attribute_map").pk)
        with self.assertRaises(UnsetFieldException):
            self.handler.get_jsonschema_instance(map_resource, FIELD, {}, {})

    # -- update ------------------------------------------------------------

    def test_update_edits_all_editable_columns(self):
        errors = self._update(
            self.dataset,
            [
                {
                    "pk": self.density.pk,
                    "attribute": "renamed",  # read-only, must be ignored
                    "attribute_type": "xsd:string",  # read-only, must be ignored
                    "attribute_label": "Soil density",
                    "description": "Dry bulk density of the soil",
                    "attribute_unit": "g/cm³",
                    "attribute_method": "Core method",
                    "display_order": 5,
                    "visible": False,
                    "featureinfo_type": Attribute.TYPE_HREF,
                }
            ],
        )

        self.assertEqual(errors, {})
        self.density.refresh_from_db()
        self.assertEqual(self.density.attribute, "soil_density")
        self.assertEqual(self.density.attribute_type, "xsd:double")
        self.assertEqual(self.density.attribute_label, "Soil density")
        self.assertEqual(self.density.description, "Dry bulk density of the soil")
        self.assertEqual(self.density.attribute_unit, "g/cm³")
        self.assertEqual(self.density.attribute_method, "Core method")
        self.assertEqual(self.density.display_order, 5)
        self.assertFalse(self.density.visible)
        self.assertEqual(self.density.featureinfo_type, Attribute.TYPE_HREF)

    def test_update_stores_empty_text_as_null(self):
        errors = self._update(self.dataset, [{"pk": self.depth.pk, "attribute_label": ""}])

        self.assertEqual(errors, {})
        self.depth.refresh_from_db()
        self.assertIsNone(self.depth.attribute_label)

    def test_update_never_touches_other_or_unknown_attributes(self):
        other_dataset = create_single_dataset("zalf_attribute_other")
        foreign = Attribute.objects.create(dataset=other_dataset, attribute="foreign", attribute_label="Foreign")

        errors = self._update(
            self.dataset,
            [
                {"pk": foreign.pk, "attribute_label": "hijacked"},
                {"pk": 999999, "attribute_label": "unknown"},
                {"attribute_label": "no pk"},
            ],
        )

        self.assertEqual(errors, {})
        foreign.refresh_from_db()
        self.assertEqual(foreign.attribute_label, "Foreign")
        self.assertEqual(self.dataset.attribute_set.count(), 2)
        self.assertEqual(other_dataset.attribute_set.filter(attribute="foreign").count(), 1)

    def test_update_reports_invalid_values_per_cell(self):
        errors = self._update(
            self.dataset,
            [
                {"pk": self.depth.pk, "attribute_label": "x" * 256, "display_order": "first"},
                {"pk": self.density.pk, "featureinfo_type": "type_unknown", "visible": "yes"},
            ],
        )

        self.assertIn("__errors", errors[FIELD]["0"]["attribute_label"])
        self.assertIn("__errors", errors[FIELD]["0"]["display_order"])
        self.assertIn("__errors", errors[FIELD]["1"]["featureinfo_type"])
        self.assertIn("__errors", errors[FIELD]["1"]["visible"])
        self.depth.refresh_from_db()
        self.density.refresh_from_db()
        self.assertEqual(self.depth.attribute_label, "Depth")
        self.assertEqual(self.depth.display_order, 1)
        self.assertEqual(self.density.featureinfo_type, Attribute.TYPE_PROPERTY)
        self.assertTrue(self.density.visible)

    def test_update_never_writes_to_the_resourcebase_columns(self):
        """context["base"] is applied with QuerySet.update(), which only accepts real columns.

        attribute_set is a related table, so leaking it there makes every metadata save fail
        with FieldDoesNotExist -- for maps and documents too.
        """
        for resource in (self.dataset, create_single_map("zalf_attribute_map_base")):
            context = {}
            self.handler.update_resource(
                resource, FIELD, {FIELD: [{"pk": self.depth.pk, "attribute_label": "Depth"}]}, context, {}
            )
            self.assertNotIn(FIELD, context.get("base", {}), resource.resource_type)

    def test_update_ignores_resources_without_attributes(self):
        map_resource = create_single_map("zalf_attribute_map_update")
        errors = self._update(map_resource, [{"pk": self.depth.pk, "attribute_label": "from a map"}])

        self.assertEqual(errors, {})
        self.depth.refresh_from_db()
        self.assertEqual(self.depth.attribute_label, "Depth")
