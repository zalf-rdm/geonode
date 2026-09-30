"""Validate real rendered ISO records against the ISO 19139 gmd.xsd.

Skipped unless a local mirror of the schema is present, because gmd.xsd pulls in ~54
imported documents and the suite must not reach the network. To populate the mirror::

    python - <<'EOF'
    import os
import unittest
    from urllib.parse import urljoin, urlparse
    from urllib.request import urlopen
    from lxml import etree
    XS, OUT = "{http://www.w3.org/2001/XMLSchema}", "/tmp/schemas"
    seen = set()
    def fetch(u):
        if u in seen:
            return
        seen.add(u)
        d = os.path.join(OUT, urlparse(u).netloc, urlparse(u).path.lstrip("/"))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if not os.path.exists(d):
            open(d, "wb").write(urlopen(u, timeout=60).read())
        for tag in ("import", "include", "redefine"):
            for el in etree.parse(d).iter(XS + tag):
                if el.get("schemaLocation"):
                    fetch(urljoin(u, el.get("schemaLocation")))
    fetch("http://www.isotc211.org/2005/gmd/gmd.xsd")
    EOF

This is the only check that catches element *placement* errors -- the Django tests can
only assert presence or absence.
"""

import os
import unittest

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from lxml import etree

from geonode.base.models import ResourceBase
from geonode.base.populate_test_data import create_single_dataset, create_single_map
from geonode.maps.models import MapLayer

SCHEMA = "/tmp/schemas/www.isotc211.org/2005/gmd/gmd.xsd"


@unittest.skipUnless(os.path.exists(SCHEMA), f"ISO 19139 schema mirror not found at {SCHEMA}")
@override_settings(CATALOG_METADATA_TEMPLATE="catalogue/zalf_metadata.xml")
class IsoSchemaValidationTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = etree.XMLSchema(etree.parse(SCHEMA))

    @staticmethod
    def with_contact(resource):
        """ISO requires at least one gmd:contact before dateStamp, and the template only
        emits contacts for the pointOfContact role. The test factories assign an owner but
        no contact roles, so without this every record is schema-invalid for a reason that
        has nothing to do with what is under test."""
        resource.poc = get_user_model().objects.get(username="admin")
        resource.save()
        return resource

    def assertValid(self, resource, label):
        xml = ResourceBase.objects.get(pk=resource.pk).metadata_xml
        doc = etree.fromstring(xml.encode("utf-8"))
        ok = self.schema.validate(doc)
        errors = "\n".join(f"  {e.line}: {e.message}" for e in self.schema.error_log)
        self.assertTrue(ok, f"{label} failed gmd.xsd validation:\n{errors}")

    def test_plain_dataset_validates(self):
        d = self.with_contact(create_single_dataset("schema_vector"))
        self.assertValid(d, "dataset")

    def test_tabular_dataset_validates(self):
        d = create_single_dataset("schema_tabular")
        d.subtype = "tabular"
        self.with_contact(d)
        self.assertValid(d, "nonGeographicDataset (extent suppressed, levelDescription present)")

    def test_series_with_members_validates(self):
        d = create_single_dataset("schema_member")
        m = create_single_map("schema_map")
        MapLayer.objects.create(map=m, dataset=d, name=d.alternate, order=0)
        self.with_contact(m)
        self.assertValid(m, "series with aggregationInfo + hierarchyLevelName")

    def test_tabular_collection_map_validates(self):
        m = self.with_contact(create_single_map("schema_tabcoll", subtype="tabular-collection"))
        self.assertValid(m, "tabular-collection series (extent suppressed)")
