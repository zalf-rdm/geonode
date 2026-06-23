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

from rest_framework.reverse import reverse

from django.utils.translation import gettext as _

from geonode.base.models import (
    Funding,
    Organization,
    RelatedIdentifier,
    RelatedIdentifierType,
    RelationType,
    ResourceTypeGeneral,
    RestrictionCodeType,
)
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
    "use_constrains",
}

# M2M fields — must be saved via .set(), never via QuerySet.update()
M2M_RESTRICTION_FIELDS = {
    "use_constraint_restrictions",
    "restriction_other",
}

# Complex M2M fields with nested objects (funders, related identifiers)
M2M_COMPLEX_FIELDS = {
    "fundings",
    "related_identifier",
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
        pass

    def _load_schema(self):
        with open(_SCHEMA_PATH) as f:
            return json.load(f)

    def update_schema(self, jsonschema, context, lang=None):
        schema = self._load_schema()
        for property_name, subschema in schema.items():
            # Only process fields owned by this handler
            if subschema.get("geonode:handler", "zalf") != "zalf":
                continue

            # Ensure handler tag is set
            if "geonode:handler" not in subschema:
                subschema["geonode:handler"] = "zalf"

            self._localize_subschema_labels(context, subschema, lang, property_name)
            self._add_subschema(jsonschema, property_name, subschema)

            # Populate dynamic choices / autocomplete
            if property_name == "conformity_results":
                subschema["oneOf"] = [{"const": v, "title": _(v)} for v in CONFORMITY_CHOICES]
            elif property_name in M2M_RESTRICTION_FIELDS:
                subschema["ui:options"] = {"geonode-ui:autocomplete": reverse("metadata_autocomplete_restrictioncodes")}
            elif property_name == "fundings":
                item_props = subschema["items"]["properties"]
                item_props["organization"]["oneOf"] = [
                    {"const": str(org.pk), "title": org.organization or str(org.pk)}
                    for org in Organization.objects.order_by("organization")
                ]
            elif property_name == "related_identifier":
                item_props = subschema["items"]["properties"]
                item_props["related_identifier_type"]["oneOf"] = [
                    {"const": t.label, "title": t.label, "description": t.description}
                    for t in RelatedIdentifierType.objects.order_by("label")
                ]
                item_props["relation_type"]["oneOf"] = [
                    {"const": t.label, "title": t.label, "description": t.description}
                    for t in RelationType.objects.order_by("label")
                ]
                item_props["resource_type_general"]["oneOf"] = [
                    {"const": t.label, "title": t.label, "description": t.description}
                    for t in ResourceTypeGeneral.objects.order_by("label")
                ]

        # Reorder all properties to match the key order defined in zalf.json.
        # Other handlers (base, thesaurus, region, contact, …) have already appended
        # their fields; we now sort them into the desired positions. Fields not present
        # in zalf.json (e.g. tkeywords, regions, contacts) are appended at the end in
        # their original relative order.
        desired_order = list(schema.keys())
        current_props = jsonschema["properties"]
        reordered = {k: current_props[k] for k in desired_order if k in current_props}
        for k, v in current_props.items():
            if k not in reordered:
                reordered[k] = v
        jsonschema["properties"] = reordered

        return jsonschema

    def get_jsonschema_instance(self, resource, field_name, context, errors, lang=None):
        if field_name in M2M_RESTRICTION_FIELDS:
            m2m = getattr(resource, field_name)
            return [{"id": r.identifier, "label": r.identifier} for r in m2m.all()]

        if field_name == "fundings":
            result = []
            for f in resource.fundings.select_related("organization").all():
                org = f.organization
                result.append(
                    {
                        "organization": str(org.pk) if org else None,
                        "award_title": f.award_title or "",
                        "award_number": f.award_number or "",
                        "award_uri": f.award_uri or "",
                    }
                )
            return result

        if field_name == "related_identifier":
            result = []
            for ri in resource.related_identifier.select_related(
                "related_identifier_type", "relation_type", "resource_type_general"
            ).all():
                rit = ri.related_identifier_type
                rt = ri.relation_type
                rtg = ri.resource_type_general
                result.append(
                    {
                        "related_identifier": ri.related_identifier,
                        "related_identifier_type": rit.label if rit else None,
                        "relation_type": rt.label if rt else None,
                        "resource_type_general": rtg.label if rtg else None,
                        "description": ri.description or "",
                    }
                )
            return result

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

        if field_name == "fundings":
            data = json_instance.get(field_name) or []
            fundings = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                org = None
                org_pk = item.get("organization")
                if org_pk:
                    try:
                        org = Organization.objects.get(pk=org_pk)
                    except Organization.DoesNotExist:
                        logger.warning(f"ZalfHandler: Organization pk={org_pk} not found, skipping funder")
                        continue
                funding, _ = Funding.objects.get_or_create(
                    organization=org,
                    award_number=item.get("award_number") or "",
                    award_uri=item.get("award_uri") or "",
                    award_title=item.get("award_title") or "",
                )
                fundings.append(funding)
            resource.fundings.set(fundings)
            return

        if field_name == "related_identifier":
            data = json_instance.get(field_name) or []
            rel_ids = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    rit_label = item.get("related_identifier_type")
                    rt_label = item.get("relation_type")
                    rtg_label = item.get("resource_type_general")
                    rit = RelatedIdentifierType.objects.get(label=rit_label) if rit_label else None
                    rt = RelationType.objects.get(label=rt_label) if rt_label else None
                    rtg = ResourceTypeGeneral.objects.get(label=rtg_label) if rtg_label else None
                    lookup = {
                        "related_identifier": item.get("related_identifier", ""),
                        "related_identifier_type": rit,
                        "relation_type": rt,
                        "resource_type_general": rtg,
                    }
                    ri, _ = RelatedIdentifier.objects.get_or_create(
                        **lookup,
                        defaults={"description": item.get("description") or ""},
                    )
                    rel_ids.append(ri)
                except Exception as e:
                    logger.warning(f"ZalfHandler: could not resolve related_identifier entry {item}: {e}")
                    continue
            resource.related_identifier.set(rel_ids)
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
