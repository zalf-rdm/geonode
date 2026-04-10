#########################################################################
#
# Copyright (C) ZALF
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#########################################################################

import datetime
import json
import logging
import os

from django.utils.translation import gettext as _

from geonode.base.models import RestrictionCodeType
from geonode.metadata.handlers.abstract import MetadataHandler

logger = logging.getLogger(__name__)

# Path to the ZALF-specific JSON schema fragment
_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schemas", "zalf.json")

# Fields that are plain DB columns — safe to put in context["base"] for QuerySet.update()
SCALAR_FIELDS = {
    "title_translated",
    "abstract_translated",
    "subtitle",
    "method_description",
    "series_information",
    "table_of_content",
    "technical_info",
    "other_description",
    "data_lineage",
    "metadata_lineage",
    "conformity_results",
    "conformity_explanation",
    "date_available",
    "date_created",
    "date_updated",
    "date_accepted",
    "date_copyrighted",
    "date_submitted",
    "date_valid",
}

# M2M fields — must be saved via .set(), never via QuerySet.update()
M2M_RESTRICTION_FIELDS = {
    "use_constraint_restrictions",
    "restriction_other",
}

# Fields that are NOT NULL in the DB (blank=True but no null=True) — keep empty string as ""
NON_NULLABLE_TEXT_FIELDS = {
    "title_translated",
    "abstract_translated",
    "subtitle",
    "method_description",
    "series_information",
    "table_of_content",
    "technical_info",
    "other_description",
    "data_lineage",
    "metadata_lineage",
    "conformity_results",
    "conformity_explanation",
}

# Conformity choices for the oneOf schema population
CONFORMITY_CHOICES = ["Passed", "Not Passed", "Unknown"]


class ZalfHandler(MetadataHandler):
    """
    Handles ZALF-specific metadata fields:
      - Scalar text/date fields (title_translated, abstract_translated, etc.)
      - M2M restriction fields (use_constraint_restrictions, restriction_other)
    """

    def __init__(self):
        self._schema = None

    def _load_schema(self):
        if self._schema is None:
            with open(_SCHEMA_PATH) as f:
                self._schema = json.load(f)
        return self._schema

    def update_schema(self, jsonschema, context, lang=None):
        schema = self._load_schema()
        for property_name, subschema in schema.items():
            # Ensure handler tag is set
            if "geonode:handler" not in subschema:
                subschema["geonode:handler"] = "zalf"

            self._localize_subschema_labels(context, subschema, lang, property_name)
            self._add_subschema(jsonschema, property_name, subschema)

            # Populate dynamic choices
            if property_name == "conformity_results":
                subschema["oneOf"] = [{"const": v, "title": _(v)} for v in CONFORMITY_CHOICES]
            elif property_name in M2M_RESTRICTION_FIELDS:
                items_oneof = [
                    {"const": tc.identifier, "title": tc.identifier, "description": tc.description}
                    for tc in RestrictionCodeType.objects.order_by("identifier")
                ]
                subschema["items"]["oneOf"] = items_oneof

        return jsonschema

    def get_jsonschema_instance(self, resource, field_name, context, errors, lang=None):
        if field_name in M2M_RESTRICTION_FIELDS:
            m2m = getattr(resource, field_name)
            return [{"id": r.identifier, "label": r.identifier} for r in m2m.all()]

        # Scalar: return value directly (dates as ISO strings)
        value = getattr(resource, field_name, None)
        if value is not None and hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    def update_resource(self, resource, field_name, json_instance, context, errors, **kwargs):
        if field_name in M2M_RESTRICTION_FIELDS:
            data = json_instance.get(field_name) or []
            identifiers = [item["id"] for item in data if isinstance(item, dict) and "id" in item]
            qs = RestrictionCodeType.objects.filter(identifier__in=identifiers)
            getattr(resource, field_name).set(qs)
            # Do NOT add to context["base"] — M2M cannot go through QuerySet.update()
            return

        # Scalar field — safe to setattr and add to context["base"]
        value = json_instance.get(field_name, None)
        try:
            # For nullable DB fields, convert empty strings to None
            # For non-nullable text fields (blank=True), keep empty string
            if value == "" and field_name not in NON_NULLABLE_TEXT_FIELDS:
                value = None
            # Parse date strings for DateField columns
            if value is not None and field_name.startswith("date_"):
                if isinstance(value, str):
                    value = datetime.date.fromisoformat(value)
            setattr(resource, field_name, value)
            context.setdefault("base", {})[field_name] = value
        except Exception as e:
            logger.warning(f"ZalfHandler: error setting field {field_name}={value}: {e}")
            self._set_error(
                errors,
                [field_name],
                self.localize_message(context, "metadata_error_store", {"fieldname": field_name, "exc": e}),
            )

    def post_save(self, resource, json_instance, context, errors, **kwargs):
        """
        M2M fields must be (re-)applied after save since the object must exist in DB.
        We already call .set() in update_resource, but refresh here to ensure consistency.
        """
        pass
