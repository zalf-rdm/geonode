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


def series_members(resource):
    """Return the published datasets a map aggregates, as (uuid, title) pairs.

    The series record lists its members rather than each member naming its parent: a
    dataset can sit in several maps while ISO allows a single gmd:parentIdentifier, so
    the child-side link would have to pick one map arbitrarily and would go stale for
    the others. Listing from the series side represents the real many-to-many shape and
    keeps dataset records untouched.

    Unpublished members are skipped so a draft never leaks into a public record.
    """
    datasets = getattr(resource, "datasets", None)
    if datasets is None:
        return []

    return [(d.uuid, d.title) for d in datasets.filter(is_published=True).order_by("pk")]


def sync_csw_type(resource):
    """Persist the scope code of ``resource`` into its ``csw_type`` column.

    Uses a queryset update rather than ``resource.save()``: this runs from a post_save
    handler, and saving again would recurse.
    """
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
