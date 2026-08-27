"""Template tags exposing the ZALF ISO scope codes to the catalogue XML template.

Follows the same shape as geonode/catalogue/templatetags/gdi_de.py: thin simple_tags
over plain functions, so the logic stays testable without rendering a template.
"""

import logging

from django import template

from geonode.zalf.catalogue import iso_scope_code, series_members

logger = logging.getLogger(__name__)

register = template.Library()


@register.simple_tag
def zalf_iso_scope_code(resource):
    """ISO MD_ScopeCode for a resource, e.g. {% zalf_iso_scope_code layer as scope_code %}."""
    return iso_scope_code(resource)


@register.simple_tag
def zalf_series_members(resource):
    """(uuid, title) pairs for the published datasets a map aggregates; empty otherwise."""
    return series_members(resource)
