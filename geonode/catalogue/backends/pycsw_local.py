#########################################################################
#
# Copyright (C) 2016 OSGeo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################

import os
from owslib.etree import etree as dlxml
from django.conf import settings
from owslib.iso import MD_Metadata
from pycsw import server
from geonode.catalogue.backends.generic import CatalogueBackend as GenericCatalogueBackend
from geonode.catalogue.backends.generic import METADATA_FORMATS
from shapely.errors import WKBReadingError, WKTReadingError

true_value = "true"
false_value = "false"
if settings.DATABASES["default"]["ENGINE"].endswith(
    (
        "sqlite",
        "sqlite3",
        "spatialite",
    )
):
    true_value = "1"
    false_value = "0"

# pycsw settings that the user shouldn't have to worry about
CONFIGURATION = {
    "server": {
        "home": ".",
        "url": settings.CATALOGUE["default"]["URL"],
        "encoding": "UTF-8",
        "language": settings.LANGUAGE_CODE,
        "maxrecords": "10",
        "pretty_print": "true",
        "domainquerytype": "range",
        "domaincounts": "true",
        "profiles": "apiso,ebrim",
    },
    "logging": {
        "level": "INFO",
    },
    "repository": {
        "source": "geonode.catalogue.backends.pycsw_plugin.GeoNodeRepository",
        "filter": "uuid IS NOT NULL",
        "mappings": os.path.join(os.path.dirname(__file__), "pycsw_local_mappings.py"),
    },
}


class CatalogueBackend(GenericCatalogueBackend):
    def __init__(self, *args, **kwargs):
        GenericCatalogueBackend.__init__(CatalogueBackend, self, *args, **kwargs)
        self.catalogue.formats = ["Atom", "DataCite", "DIF", "Dublin Core", "ebRIM", "FGDC", "ISO"]
        self.catalogue.local = True

    def remove_record(self, uuid):
        pass

    def create_record(self, item):
        pass

    def get_record(self, uuid):
        results = self._csw_local_dispatch(identifier=uuid)
        if len(results) < 1:
            return None

        result = dlxml.fromstring(results).find("{http://www.isotc211.org/2005/gmd}MD_Metadata")

        if result is None:
            return None

        record = MD_Metadata(result)
        record.keywords = []
        if hasattr(record, "identification") and hasattr(record.identification[0], "keywords"):
            for kw in record.identification[0].keywords:
                record.keywords.extend([_kw.name for _kw in kw.keywords])

        record.links = {}
        record.links["metadata"] = self.catalogue.urls_for_uuid(uuid)
        record.links["download"] = self.catalogue.extract_links(record)
        return record

    def get_datacite_record(self, uuid):
        """Get DataCite XML metadata for a resource by UUID.

        Returns the inner <resource> DataCite XML element serialised as a
        string, unwrapped from the CSW GetRecordByIdResponse envelope that
        pycsw wraps around every record.
        """
        from owslib.etree import etree as _etree

        DATACITE_NS = "http://datacite.org/schema/kernel-4"
        CSW_NS = "http://www.opengis.net/cat/csw/2.0.2"

        response = self._csw_local_dispatch(
            identifier=uuid,
            outputschema=METADATA_FORMATS["DataCite"][1],
        )
        if not response or len(response) < 1:
            return None

        # response is the serialised CSW envelope; unwrap it to get the inner
        # DataCite <resource> element.
        import logging as _logging

        _logger = _logging.getLogger(__name__)
        _logger.debug(f"get_datacite_record raw pycsw response for {uuid}: {response[:2000] if response else None}")
        try:
            root = _etree.fromstring(response if isinstance(response, bytes) else response.encode("utf-8"))
        except Exception as exc:
            _logger.warning(f"get_datacite_record: failed to parse pycsw response for {uuid}: {exc}")
            return None

        # pycsw wraps the record inside <csw:GetRecordByIdResponse>
        # Try to find the DataCite <resource> element directly.
        resource_el = root.find(f"{{{DATACITE_NS}}}resource")
        if resource_el is None:
            # Fallback: search anywhere in the tree
            resource_el = root.find(f".//{{{DATACITE_NS}}}resource")
        if resource_el is None:
            return None

        return _etree.tostring(resource_el, encoding="unicode")

    def search_records(self, keywords, start, limit, bbox):
        with self.catalogue:
            lresults = self._csw_local_dispatch(keywords, keywords, start + 1, limit, bbox)
            # serialize XML
            e = dlxml.fromstring(lresults)

            self.catalogue.records = [
                MD_Metadata(x) for x in e.findall("//{http://www.isotc211.org/2005/gmd}MD_Metadata")
            ]

            # build results into JSON for API
            results = [self.catalogue.metadatarecord2dict(doc) for v, doc in self.catalogue.records.items()]

            result = {
                "rows": results,
                "total": e.find("{http://www.opengis.net/cat/csw/2.0.2}SearchResults").attrib.get(
                    "numberOfRecordsMatched"
                ),
                "next_page": e.find("{http://www.opengis.net/cat/csw/2.0.2}SearchResults").attrib.get("nextRecord"),
            }

            return result

    def _csw_local_dispatch(self, keywords=None, start=0, limit=10, bbox=None, identifier=None, outputschema=None):
        """
        HTTP-less CSW
        """

        mdict = dict(settings.PYCSW["CONFIGURATION"], **CONFIGURATION)
        if "server" in settings.PYCSW["CONFIGURATION"]:
            # override server system defaults with user specified directives
            mdict["server"].update(settings.PYCSW["CONFIGURATION"]["server"])

        # fake HTTP environment variable
        os.environ["QUERY_STRING"] = ""

        # init pycsw
        csw = server.Csw(mdict, version="2.0.2")

        # fake HTTP method
        csw.requesttype = "GET"

        # fake HTTP request parameters
        if identifier is None:  # it's a GetRecords request
            formats = []
            for f in self.catalogue.formats:
                formats.append(METADATA_FORMATS[f][0])

            csw.kvp = {
                "service": "CSW",
                "version": "2.0.2",
                "elementsetname": "full",
                "typenames": formats,
                "resulttype": "results",
                "constraintlanguage": "CQL_TEXT",
                "outputschema": "http://www.isotc211.org/2005/gmd",
                "constraint": None,
                "startposition": start,
                "maxrecords": limit,
            }
            response = csw.getrecords2()
        else:  # it's a GetRecordById request
            csw.kvp = {
                "service": "CSW",
                "version": "2.0.2",
                "request": "GetRecordById",
                "id": identifier,
                "outputschema": outputschema or "http://www.isotc211.org/2005/gmd",
            }
            # FIXME(Ariel): Remove this try/except block when pycsw deals with
            # empty geometry fields better.
            # https://gist.github.com/ingenieroariel/717bb720a201030e9b3a
            try:
                response = csw.dispatch()
            except (WKBReadingError, WKTReadingError):
                return []

        if isinstance(response, list):  # pycsw 2.0+
            response = response[1]

        return response
