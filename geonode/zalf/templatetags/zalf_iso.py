"""Template tags exposing the ZALF ISO scope codes to the catalogue XML template.

Follows the same shape as geonode/catalogue/templatetags/gdi_de.py: thin simple_tags
over plain functions, so the logic stays testable without rendering a template.
"""

import logging

from django import template

from geonode.zalf.catalogue import iso_scope_code, parent_series_uuid

logger = logging.getLogger(__name__)

register = template.Library()


@register.simple_tag
def zalf_iso_scope_code(resource):
    """ISO MD_ScopeCode for a resource, e.g. {% zalf_iso_scope_code layer as scope_code %}."""
    return iso_scope_code(resource)


@register.simple_tag
def zalf_parent_series_uuid(resource):
    """uuid of the map a dataset belongs to, or empty string when it belongs to none."""
    return parent_series_uuid(resource) or ""
