"""Catalogue signal wiring for ZALF.

Two jobs:

1. Put maps into the catalogue at all. Upstream connects ``catalogue_post_save`` only
   for Dataset and Document (geonode/catalogue/models.py), so maps have never had their
   ``metadata_xml`` generated -- they carry the empty ``<gmd:MD_Metadata/>`` default.
   Exposing maps over CSW without this would publish empty records.

2. Keep the ISO scope code in sync in both places it lives: the ``csw_type`` column and
   the stored ISO XML. Member datasets of a map carry the map's uuid as
   ``gmd:parentIdentifier``, so they have to be regenerated whenever a map's membership
   changes or the map goes away.
"""

import logging

from django.db.models import signals

from geonode.catalogue.models import catalogue_post_save, catalogue_pre_delete
from geonode.layers.models import Dataset
from geonode.maps.models import Map
from geonode.zalf.catalogue import regenerate_metadata, sync_csw_type

logger = logging.getLogger(__name__)

# Attribute used to carry a map's members from pre_delete to post_delete: by the time
# post_delete fires the MapLayer rows are gone, so the members cannot be looked up.
_PENDING_MEMBERS_ATTR = "_zalf_pending_series_members"


def sync_resource_csw_type(instance, sender, **kwargs):
    """Persist the ISO scope code of a saved resource into its csw_type column."""
    sync_csw_type(instance)


def sync_series_members(instance, sender, **kwargs):
    """Refresh the ISO XML of the datasets a map aggregates.

    Safe to read membership here: MapViewSet.create/update commit the ``maplayers``
    m2m before the object change, so the maplayers are already written when the Map
    post_save fires.
    """
    regenerate_metadata(instance.datasets)


def stash_series_members(instance, sender, **kwargs):
    """Remember a map's members before it is deleted."""
    setattr(instance, _PENDING_MEMBERS_ATTR, list(instance.datasets))


def refresh_orphaned_series_members(instance, sender, **kwargs):
    """Drop the now-dangling parentIdentifier from a deleted map's former members."""
    members = getattr(instance, _PENDING_MEMBERS_ATTR, None)
    if members:
        regenerate_metadata(members)


def connect():
    """Connect the ZALF catalogue signals. Called from the AppConfig's setup hooks."""
    # Maps need the same catalogue treatment datasets and documents already get.
    signals.post_save.connect(catalogue_post_save, sender=Map, dispatch_uid="zalf_map_catalogue_post_save")
    signals.pre_delete.connect(catalogue_pre_delete, sender=Map, dispatch_uid="zalf_map_catalogue_pre_delete")

    # Keep csw_type (pycsw:Type / apiso:Type) aligned with the ISO scope code.
    for sender in (Dataset, Map):
        signals.post_save.connect(
            sync_resource_csw_type,
            sender=sender,
            dispatch_uid=f"zalf_sync_csw_type_{sender.__name__.lower()}",
        )

    # Members carry the map uuid as gmd:parentIdentifier, so they follow the map.
    signals.post_save.connect(sync_series_members, sender=Map, dispatch_uid="zalf_sync_series_members")
    signals.pre_delete.connect(stash_series_members, sender=Map, dispatch_uid="zalf_stash_series_members")
    signals.post_delete.connect(
        refresh_orphaned_series_members, sender=Map, dispatch_uid="zalf_refresh_orphaned_series_members"
    )

    logger.debug("ZALF catalogue signals connected")
