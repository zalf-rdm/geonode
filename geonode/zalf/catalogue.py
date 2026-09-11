"""ISO 19115 scope codes for the ZALF catalogue.

GeoNode publishes every CSW record as ``<gmd:MD_ScopeCode codeListValue="dataset">``,
which leaves harvesters (FAIRagro in particular) unable to tell a map from a plain
dataset, or a table from something with a real geographic extent. This module is the
single place that decides which ISO scope code a resource gets; both the ISO XML
template and the ``csw_type`` column derive from it, so the two can never disagree.

Why both: pycsw dumps the stored ``metadata_xml`` verbatim for full ISO records, but
builds brief/summary records itself from ``csw_type`` (mapped to ``pycsw:Type``), and
``csw_type`` is also what backs the ``apiso:Type`` queryable harvesters filter on.
"""

import logging

from geonode.base.models import ResourceBase

logger = logging.getLogger(__name__)

# Values from geonode.base.enumerations.HIERARCHY_LEVELS -- the MD_ScopeCode codelist.
ISO_SCOPE_DATASET = "dataset"
ISO_SCOPE_SERIES = "series"
ISO_SCOPE_NON_GEOGRAPHIC = "nonGeographicDataset"

# Dataset subtypes that carry no geography. The datapackage importer stamps imported
# tables with "tabular" and gives them a placeholder world bbox, so the subtype is the
# only honest signal that the resource is non-geographic.
NON_GEOGRAPHIC_SUBTYPES = ("tabular",)

# Map subtypes that aggregate only non-geographic members. Such a map is still an ISO
# "series" (it is a collection), but it has no meaningful extent of its own -- the union
# of its members' placeholder world bboxes is just the world again.
NON_GEOGRAPHIC_MAP_SUBTYPES = ("tabular-collection",)

# DS_AssociationTypeCode used for the series -> member links. ISO 19115-1 has a precise
# "isComposedOf", but these records cite the 2005 gmxCodelists codelist, whose
# DS_AssociationTypeCode has no whole-to-part value -- crossReference is its generic one.
SERIES_ASSOCIATION_TYPE = "crossReference"


def iso_scope_code(resource):
    """Return the ISO MD_ScopeCode for ``resource``.

    Maps aggregate datasets, so they are a "series" -- including the ZALF-specific
    ``tabular-collection`` maps, which are a series of non-geographic members but a
    series all the same.
    """
    resource_type = getattr(resource, "resource_type", None)

    if resource_type == "map":
        return ISO_SCOPE_SERIES

    if resource_type == "dataset" and getattr(resource, "subtype", None) in NON_GEOGRAPHIC_SUBTYPES:
        return ISO_SCOPE_NON_GEOGRAPHIC

    return ISO_SCOPE_DATASET


def is_non_geographic(resource):
    """True when ``resource`` has no meaningful geographic extent.

    Deliberately broader than ``iso_scope_code(...) == ISO_SCOPE_NON_GEOGRAPHIC``: a
    ``tabular-collection`` map is a *series* by scope code, yet publishing an extent for a
    collection of tables would claim worldwide coverage just the same.
    """
    resource_type = getattr(resource, "resource_type", None)
    subtype = getattr(resource, "subtype", None)

    if resource_type == "dataset":
        return subtype in NON_GEOGRAPHIC_SUBTYPES
    if resource_type == "map":
        return subtype in NON_GEOGRAPHIC_MAP_SUBTYPES
    return False


def _maplayer_names(dataset):
    """The MapLayer.name values that identify ``dataset``."""
    return [n for n in (getattr(dataset, "alternate", None), getattr(dataset, "name", None)) if n]


def series_member_datasets(map_obj):
    """Published datasets a map aggregates.

    Membership is resolved by the ``MapLayer.dataset`` FK *or* by ``MapLayer.name``
    matching. Upstream's two accessors disagree -- ``Map.datasets`` matches on name only
    while ``Dataset.maps`` follows the FK -- so a layer with one but not the other is
    visible from one direction and invisible from the other. Both directions here go
    through this same criterion (see ``owning_series``) so the series record and the
    refresh that keeps it current can never disagree about who belongs to what.
    """
    from django.db.models import Q
    from geonode.layers.models import Dataset
    from geonode.maps.models import MapLayer

    layers = MapLayer.objects.filter(map=map_obj)
    fk_ids = [pk for pk in layers.values_list("dataset_id", flat=True) if pk]
    names = [name for name in layers.values_list("name", flat=True) if name]

    return (
        Dataset.objects.filter(Q(pk__in=fk_ids) | Q(alternate__in=names) | Q(name__in=names))
        .filter(is_published=True)
        .distinct()
        .order_by("pk")
    )


def owning_series(dataset):
    """Maps that aggregate ``dataset``, by the same criterion as ``series_member_datasets``."""
    from django.db.models import Q
    from geonode.maps.models import Map, MapLayer

    names = _maplayer_names(dataset)
    layers = (
        MapLayer.objects.filter(Q(dataset=dataset) | Q(name__in=names))
        if names
        else MapLayer.objects.filter(dataset=dataset)
    )
    return Map.objects.filter(pk__in=layers.values_list("map_id", flat=True)).distinct()


def series_members(resource):
    """Return the uuids of the published datasets a map aggregates.

    Uuids only: that is exactly what the record references, and keeping the return value
    aligned with what is embedded means the refresh fingerprint in signals.py can be
    trusted (a member attribute the record does not carry must not trigger a re-render).

    The series record lists its members rather than each member naming its parent: a
    dataset can sit in several maps while ISO allows exactly one gmd:parentIdentifier, so
    the child-side link would have to pick one map arbitrarily and would go stale for the
    others. Listing from the series side represents the real many-to-many shape and keeps
    dataset records untouched.

    Unpublished members are skipped so a draft never leaks into a public record.
    """
    if getattr(resource, "resource_type", None) != "map":
        return []

    return list(series_member_datasets(resource).values_list("uuid", flat=True))


def preserves_custom_xml(resource):
    """True when the resource carries user-uploaded XML that must not be derived over."""
    return bool(getattr(resource, "metadata_uploaded", False)) and bool(
        getattr(resource, "metadata_uploaded_preserve", False)
    )


def sync_csw_type(resource):
    """Persist the scope code of ``resource`` into its ``csw_type`` column.

    Uses a queryset update rather than ``resource.save()``: this runs from a post_save
    handler, and saving again would recurse.

    Skips resources that preserve uploaded XML. ``csw_type`` drives dc:type and the
    hierarchyLevel of brief/summary records, while the preserved XML drives the full one;
    deriving one without the other would make the two contradict each other.
    """
    if preserves_custom_xml(resource):
        return

    scope_code = iso_scope_code(resource)
    pk = resource.resourcebase_ptr_id if hasattr(resource, "resourcebase_ptr_id") else resource.pk
    if pk is None:
        return

    ResourceBase.objects.filter(pk=pk).update(csw_type=scope_code)


def regenerate_metadata(resources):
    """Rebuild the stored ISO XML for each resource in ``resources``.

    Used when a map's membership changes: the members' ``gmd:parentIdentifier`` is
    baked into their stored XML, so it goes stale unless they are regenerated.
    """
    # Imported here rather than at module scope: geonode.catalogue.models connects the
    # catalogue signals on import, and this module is itself imported from an AppConfig.
    from geonode.catalogue.models import catalogue_post_save

    for resource in resources:
        try:
            catalogue_post_save(instance=resource, sender=resource.__class__)
        except Exception:
            # One bad member must not abort the rest, nor the map save that triggered us.
            logger.exception(f"Could not regenerate catalogue metadata for resource {resource.pk}")
