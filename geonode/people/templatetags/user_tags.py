from django import template
from django.utils.safestring import mark_safe

from geonode.people.utils import get_user_display_name

register = template.Library()


@register.filter(name="display_name")
def display_name(user):
    if not user:
        return ""
    return mark_safe(get_user_display_name(user))
