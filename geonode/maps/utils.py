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

"""
Utility functions for comparing and syncing metadata between a Map
and its linked resources (datasets, documents, geoapps, maplayer datasets).
"""

import logging

from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist

from django.utils.html import strip_tags

from geonode.base.models import (
    ContactRole,
    LinkedResource,
    ResourceBase,
)

logger = logging.getLogger("geonode.maps.utils")

# Simple (scalar / FK) fields to compare and sync.
# uuid, alternate, resource_type, subtype, blob
# are intentionally excluded.
SYNC_SIMPLE_FIELDS = [
    "title",
    "title_translated",
    "abstract",
    "abstract_translated",
    "subtitle",
    "method_description",
    "series_information",
    "table_of_content",
    "technical_info",
    "other_description",
    "purpose",
    "date",
    "date_type",
    "edition",
    "attribution",
    "doi",
    "maintenance_frequency",
    "language",
    "category",
    "spatial_representation_type",
    "temporal_extent_start",
    "temporal_extent_end",
    "supplemental_information",
    "data_quality_statement",
    "license",
    "data_lineage",
    "metadata_license",
    "metadata_lineage",
    "use_constrains",
    "constraints_other",
    "conformity_results",
    "conformity_explanation",
    "date_available",
    "date_created",
    "date_issued",
    "date_updated",
    "date_accepted",
    "date_copyrighted",
    "date_submitted",
    "date_valid",
    "group",
    "is_published",
    "is_approved",
]

# Many-to-many fields to compare and sync.
SYNC_M2M_FIELDS = [
    "keywords",
    "tkeywords",
    "regions",
    "related_projects",
    "fundings",
    "related_identifier",
    "use_constraint_restrictions",
    "restriction_other",
]


# Special field name used for contact roles (not a real model field).
_CONTACT_ROLES_FIELD = "contact_roles"


def get_all_syncable_fields():
    """
    Return a list of dicts describing every field that can be synced.
    Each dict has:
        {
            "field": str,   # internal field name (matches compare_metadata output)
            "label": str,   # human-readable label
            "is_m2m": bool,
        }
    Useful for rendering a field-selection UI.
    """
    result = []
    fields_to_process = (
        (SYNC_SIMPLE_FIELDS, False),
        (SYNC_M2M_FIELDS, True)
    )

    for field_list, is_m2m in fields_to_process:
        for field_name in field_list:
            try:
                field_obj = ResourceBase._meta.get_field(field_name)
                label = str(field_obj.verbose_name).capitalize()
            except FieldDoesNotExist:
                label = field_name.replace("_", " ").title()
            result.append({"field": field_name, "label": label, "is_m2m": is_m2m})

    result.append({"field": _CONTACT_ROLES_FIELD, "label": "Contact Roles", "is_m2m": True})

    return result


def _field_display_value(obj, field_name):
    """Return a human-readable display value for a field (with HTML stripped)."""
    val = getattr(obj, field_name, None)
    if val is None:
        return ""
    # FK fields – show str representation
    if hasattr(val, "pk"):
        return str(val)
    return strip_tags(str(val))


def _m2m_display_value(obj, field_name):
    """Return a sorted list of string representations for an M2M field."""
    manager = getattr(obj, field_name, None)
    if manager is None:
        return []
    return sorted(str(item) for item in manager.all())


def get_syncable_resources(map_obj):
    """
    Return a list of ResourceBase instances that are linked to *map_obj*:
      1. Explicit LinkedResource targets (non-internal)
      2. MapLayer datasets (internal linked resources)
    De-duplicated by pk.
    """
    from geonode.maps.models import MapLayer

    seen = set()
    resources = []

    # 1. Explicit linked resources (non-internal)
    for lr in LinkedResource.get_linked_resources(source=map_obj, is_internal=False):
        target = lr.target.get_real_instance()
        if target.pk not in seen:
            seen.add(target.pk)
            resources.append(target)

    # 2. MapLayer datasets
    for ml in MapLayer.objects.filter(map=map_obj).select_related("dataset"):
        if ml.dataset_id and ml.dataset_id not in seen:
            seen.add(ml.dataset_id)
            try:
                ds = ml.dataset.get_real_instance()
                resources.append(ds)
            except (AttributeError, ObjectDoesNotExist):
                logger.warning("Could not resolve dataset for MapLayer %s", ml.pk)

    return resources


def compare_metadata(map_obj, resource):
    """
    Compare metadata between *map_obj* and a single *resource*.

    Returns a list of dicts:
        [
            {
                "field": "abstract",
                "label": "Abstract",
                "map_value": "...",
                "resource_value": "...",
                "match": True/False,
                "is_m2m": False,
            },
            ...
        ]
    """
    diffs = []

    for field_name in SYNC_SIMPLE_FIELDS:
        try:
            field_obj = ResourceBase._meta.get_field(field_name)
            label = str(field_obj.verbose_name)
        except FieldDoesNotExist:
            label = field_name.replace("_", " ").title()

        map_val = _field_display_value(map_obj, field_name)
        res_val = _field_display_value(resource, field_name)
        diffs.append(
            {
                "field": field_name,
                "label": label,
                "map_value": map_val,
                "resource_value": res_val,
                "match": map_val == res_val,
                "is_m2m": False,
            }
        )

    for field_name in SYNC_M2M_FIELDS:
        try:
            field_obj = ResourceBase._meta.get_field(field_name)
            label = str(field_obj.verbose_name)
        except FieldDoesNotExist:
            label = field_name.replace("_", " ").title()

        map_vals = _m2m_display_value(map_obj, field_name)
        res_vals = _m2m_display_value(resource, field_name)
        diffs.append(
            {
                "field": field_name,
                "label": label,
                "map_value": ", ".join(map_vals) if map_vals else "—",
                "resource_value": ", ".join(res_vals) if res_vals else "—",
                "match": map_vals == res_vals,
                "is_m2m": True,
            }
        )

    # Contact roles
    map_roles = _get_contact_roles_display(map_obj)
    res_roles = _get_contact_roles_display(resource)
    diffs.append(
        {
            "field": "contact_roles",
            "label": "Contact Roles",
            "map_value": map_roles,
            "resource_value": res_roles,
            "match": map_roles == res_roles,
            "is_m2m": True,
        }
    )

    return diffs


def _get_contact_roles_display(resource):
    """Return a sorted string representation of all contact roles."""
    roles = ContactRole.objects.filter(resource=resource).order_by("role", "order", "id")
    parts = []
    for cr in roles:
        parts.append(f"{cr.get_role_display()}: {cr.contact}")
    return "; ".join(parts) if parts else "—"


def sync_metadata(map_obj, resource, field_names=None):
    """
    Copy syncable metadata from *map_obj* to *resource* and save.
    title and title_translated are intentionally NOT synced.

    Args:
        map_obj:     Source Map instance.
        resource:    Target ResourceBase instance.
        field_names: Optional iterable of field names to sync.
                     When None (default), all syncable fields are synced.
    """
    # Resolve which fields to sync
    if field_names is None:
        simple_fields = SYNC_SIMPLE_FIELDS
        m2m_fields = SYNC_M2M_FIELDS
        sync_contact_roles = True
    else:
        field_set = set(field_names)
        simple_fields = [f for f in SYNC_SIMPLE_FIELDS if f in field_set]
        m2m_fields = [f for f in SYNC_M2M_FIELDS if f in field_set]
        sync_contact_roles = _CONTACT_ROLES_FIELD in field_set

    # 1. Simple fields
    for field_name in simple_fields:
        try:
            val = getattr(map_obj, field_name)
            setattr(resource, field_name, val)
        except AttributeError:
            logger.warning("Could not sync field %s to resource %s", field_name, resource.pk)

    if simple_fields:
        resource.save()

    # 2. M2M fields
    for field_name in m2m_fields:
        try:
            src_manager = getattr(map_obj, field_name)
            dst_manager = getattr(resource, field_name)

            if field_name == "keywords":
                # Keywords use TaggableManager – need special handling
                dst_manager.clear()
                dst_manager.add(*list(src_manager.all()))
            elif field_name in ("fundings", "related_identifier"):
                # These are shared objects referenced via M2M.
                # We set the same set of references.
                dst_manager.set(list(src_manager.all()))
            else:
                dst_manager.set(list(src_manager.all()))
        except (AttributeError, TypeError):
            logger.warning("Could not sync M2M field %s to resource %s", field_name, resource.pk)

    # 3. Contact roles
    if sync_contact_roles:
        _sync_contact_roles(map_obj, resource)


def _sync_contact_roles(map_obj, resource):
    """Copy contact roles from map_obj to resource."""
    try:
        # Delete existing contact roles on the target resource
        ContactRole.objects.filter(resource=resource).delete()

        # Copy all contact roles from map
        for cr in ContactRole.objects.filter(resource=map_obj).order_by("role", "order", "id"):
            ContactRole.objects.create(
                resource=resource,
                contact=cr.contact,
                role=cr.role,
                order=cr.order,
            )
    except (ObjectDoesNotExist, AttributeError) as exc:
        logger.exception("Could not sync contact roles to resource %s: %s", resource.pk, exc)
