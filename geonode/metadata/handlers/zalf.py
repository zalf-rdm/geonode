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

from django.core.exceptions import FieldDoesNotExist
from django.utils.translation import gettext as _

from geonode.base.models import (
    Funding,
    GeoKeyword,
    Organization,
    RelatedIdentifier,
    RelatedIdentifierType,
    RelationType,
    ResourceTypeGeneral,
    RestrictionCodeType,
)
from geonode.layers.models import Attribute
from geonode.metadata.exceptions import UnsetFieldException
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
    "geo_keywords",
}

# Whether a scalar column accepts NULL is read off the model itself (see _coerce_scalar below)
# rather than from a hand-maintained list: the list left out the NOT NULL date_* columns, and a
# list can drift from the model, while the model cannot drift from itself.

# Conformity choices for the oneOf schema population
CONFORMITY_CHOICES = ["Passed", "Not Passed", "Unknown"]

# Editable text columns of a dataset's attribute table and their max_length on the Attribute model
ATTRIBUTE_TEXT_FIELDS = {
    "attribute_label": 255,
    "description": 2048,
    "attribute_unit": 50,
    "attribute_method": 2000,
}


class ZalfHandler(MetadataHandler):
    """
    Handles ZALF-specific metadata fields:
      - Scalar text/date fields (title_translated, abstract_translated, etc.)
      - M2M restriction fields (use_constraint_restrictions, restriction_other)
      - The attribute table of datasets (attribute_set: labels, descriptions, units, methods, ...)
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
            elif property_name == "attribute_set":
                item_props = subschema["items"]["properties"]
                item_props["featureinfo_type"]["oneOf"] = [
                    {"const": value, "title": str(label)} for value, label in Attribute.TYPES
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
        if field_name == "geo_keywords":
            return list(resource.geo_keywords.values("source", "level", "layer_name", "gid", "name"))

        if field_name == "attribute_set":
            dataset = resource.get_real_instance()
            if not hasattr(dataset, "attribute_set"):
                # only datasets have attributes; leave the field out so the client hides it
                raise UnsetFieldException()
            return [
                {
                    "pk": a.pk,
                    "attribute": a.attribute or "",
                    "attribute_type": a.attribute_type or "",
                    "attribute_label": a.attribute_label or "",
                    "description": a.description or "",
                    "attribute_unit": a.attribute_unit or "",
                    "attribute_method": a.attribute_method or "",
                    "display_order": a.display_order,
                    "visible": a.visible,
                    "featureinfo_type": a.featureinfo_type,
                }
                for a in dataset.attribute_set.order_by("display_order", "pk")
            ]
        if field_name == "geo_keywords":
            return list(resource.geo_keywords.values("source", "level", "layer_name", "gid", "name"))

        # Scalar: return value directly (dates as ISO strings)
        value = getattr(resource, field_name, None)
        if value is not None and hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    @staticmethod
    def _coerce_scalar(resource, field_name, value):
        """Map a JSON value onto what the column can actually store.

        A metadata payload does not have to carry every ZALF field -- the metadata API accepts
        partial documents, and `json_instance.get(field_name)` then yields None. Several of these
        columns are NOT NULL (all the text fields, plus date_available/date_created/date_updated),
        so that None reached the QuerySet.update() and the save died with

            IntegrityError: null value in column "abstract_translated" ... violates not-null

        taking the entire metadata update with it. Missing values now fall back to the field's own
        default ("" for text, "Unknown" for conformity_results, today for the dates).
        """
        try:
            field = resource._meta.get_field(field_name)
        except FieldDoesNotExist:
            return value

        if value is None and not field.null:
            return field.get_default()
        # Nullable columns record "not set" as NULL, not as an empty string.
        if value == "" and field.null:
            return None
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

        if field_name == "attribute_set":
            # rows are saved directly on the Attribute model; nothing goes to context["base"],
            # which only takes real ResourceBase columns (QuerySet.update())
            self._update_attributes(resource, field_name, json_instance.get(field_name), context, errors)
            return

        if field_name == "geo_keywords":
            data = json_instance.get(field_name) or []
            geo_keywords = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    geo_keywords.append(
                        GeoKeyword.objects.get(
                            source=item.get("source"),
                            gid=item.get("gid"),
                        )
                    )
                except GeoKeyword.DoesNotExist:
                    self._set_error(
                        errors,
                        [field_name],
                        _("Geographic keyword %(source)s:%(gid)s does not exist.")
                        % {
                            "source": item.get("source"),
                            "gid": item.get("gid"),
                        },
                    )
            if not errors.get(field_name):
                resource.geo_keywords.set(geo_keywords)
            return

        # Scalar field — safe to setattr and add to context["base"]
        value = json_instance.get(field_name, None)
        try:
            value = self._coerce_scalar(resource, field_name, value)
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

    def _update_attributes(self, resource, field_name, data, context, errors):
        """Edit the attribute table of a dataset.

        Rows are matched by pk within this dataset. Attributes are never created or deleted here:
        GeoServer and the importers own the attribute list, so unknown pks are ignored and rows
        missing from the payload stay untouched. An invalid value is reported on its cell and
        leaves that value unchanged.
        """
        dataset = resource.get_real_instance()
        if not hasattr(dataset, "attribute_set") or not isinstance(data, list):
            return
        attributes = {a.pk: a for a in dataset.attribute_set.all()}
        featureinfo_types = {value for value, _label in Attribute.TYPES}

        def cell_error(index, name, message):
            self._set_error(
                errors,
                [field_name, str(index), name],
                self.localize_message(context, "metadata_error_store", {"fieldname": name, "exc": message}),
            )

        for index, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            attribute = attributes.get(item.get("pk"))
            if attribute is None:
                logger.warning(
                    f"ZalfHandler: attribute pk={item.get('pk')} does not belong to dataset {dataset.pk}, skipping"
                )
                continue

            changed = []
            for name, max_length in ATTRIBUTE_TEXT_FIELDS.items():
                if name not in item:
                    continue
                value = item[name] or None  # empty text is stored as NULL
                if value is not None and (not isinstance(value, str) or len(value) > max_length):
                    cell_error(index, name, f"expected text of at most {max_length} characters")
                    continue
                if getattr(attribute, name) != value:
                    setattr(attribute, name, value)
                    changed.append(name)

            if "display_order" in item:
                value = item["display_order"]
                if isinstance(value, bool) or not isinstance(value, int):
                    cell_error(index, "display_order", "expected an integer")
                elif attribute.display_order != value:
                    attribute.display_order = value
                    changed.append("display_order")

            if "visible" in item:
                value = item["visible"]
                if not isinstance(value, bool):
                    cell_error(index, "visible", "expected true or false")
                elif attribute.visible != value:
                    attribute.visible = value
                    changed.append("visible")

            if "featureinfo_type" in item:
                value = item["featureinfo_type"]
                if value not in featureinfo_types:
                    cell_error(index, "featureinfo_type", f"unknown feature info type {value!r}")
                elif attribute.featureinfo_type != value:
                    attribute.featureinfo_type = value
                    changed.append("featureinfo_type")

            if changed:
                attribute.save(update_fields=changed)

    def post_save(self, resource, json_instance, context, errors, **kwargs):
        """
        M2M fields must be (re-)applied after save since the object must exist in DB.
        We already call .set() in update_resource, but refresh here to ensure consistency.
        """
        pass
