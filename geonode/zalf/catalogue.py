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


def parent_series_uuid(resource):
    """Return the uuid of the map ``resource`` belongs to, or None.

    A dataset can sit in several maps while ISO allows exactly one parent, so pick the
    oldest published one: deterministic, and stable as further maps are added later.
    Unpublished maps are skipped so a draft's uuid never leaks into a public record.
    """
    maps = getattr(resource, "maps", None)
    if maps is None:
        return None

    parent = maps.filter(is_published=True).order_by("pk").first()
    return parent.uuid if parent else None


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
