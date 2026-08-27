"""Catalogue signal wiring for ZALF.

Two jobs:

1. Put maps into the catalogue at all. Upstream connects ``catalogue_post_save`` only
   for Dataset and Document (geonode/catalogue/models.py), so maps have never had their
   ``metadata_xml`` generated -- they carry the empty ``<gmd:MD_Metadata/>`` default.
   Exposing maps over CSW without this would publish empty records.

2. Keep the ISO scope code in sync in both places it lives: the ``csw_type`` column and
   the stored ISO XML. A map's record lists its member datasets, so the map has to be
   regenerated whenever one of its members changes, is unpublished, or is deleted.
"""

import logging

from django.db.models import signals

from geonode.catalogue.models import catalogue_post_save, catalogue_pre_delete
from geonode.layers.models import Dataset
from geonode.maps.models import Map
from geonode.zalf.catalogue import regenerate_metadata, sync_csw_type

logger = logging.getLogger(__name__)

# Carries a dataset's owning maps from pre_delete to post_delete. MapLayer.dataset is
# on_delete=SET_NULL, so by post_delete the link is already gone and the maps can no
# longer be looked up from the instance.
_PENDING_SERIES_ATTR = "_zalf_pending_owning_series"


def sync_resource_csw_type(instance, sender, **kwargs):
    """Persist the ISO scope code of a saved resource into its csw_type column."""
    sync_csw_type(instance)


def refresh_owning_series(instance, sender, **kwargs):
    """Regenerate the ISO XML of every map that aggregates this dataset.

    The series record lists its members (gmd:aggregationInfo), so a map's XML goes stale
    whenever a member's title changes, a member is unpublished, or a member is deleted.
    The dependency runs member -> series, so the refresh has to run in that direction too.
    """
    maps = getattr(instance, "maps", None)
    if maps is not None:
        regenerate_metadata(maps.all())


def stash_owning_series(instance, sender, **kwargs):
    """Remember a dataset's maps before the MapLayer link is nulled out."""
    maps = getattr(instance, "maps", None)
    setattr(instance, _PENDING_SERIES_ATTR, list(maps.all()) if maps is not None else [])


def refresh_orphaned_series(instance, sender, **kwargs):
    """Drop a deleted dataset from the aggregationInfo of the maps that listed it."""
    stashed = getattr(instance, _PENDING_SERIES_ATTR, None)
    if stashed:
        regenerate_metadata(stashed)


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

    # A series lists its members, so member changes invalidate the map's record.
    signals.post_save.connect(refresh_owning_series, sender=Dataset, dispatch_uid="zalf_refresh_owning_series")
    signals.pre_delete.connect(stash_owning_series, sender=Dataset, dispatch_uid="zalf_stash_owning_series")
    signals.post_delete.connect(refresh_orphaned_series, sender=Dataset, dispatch_uid="zalf_refresh_orphaned_series")

    logger.debug("ZALF catalogue signals connected")
