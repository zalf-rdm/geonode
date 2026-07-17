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

from django import forms
from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from geonode.base.admin import set_user_and_group_dataset_permission

from . import models


def group_member_user_label(user):
    """Human-readable label for a user in the group member picker.

    Falls back through: "First Last", then department, then username. When a
    name or department is shown, the username (which may be an opaque ORCID id)
    is appended in parentheses so the account stays identifiable.
    """
    username = user.get_username()
    if user.first_name and user.last_name:
        display = f"{user.first_name} {user.last_name}"
    elif user.department:
        display = user.department
    else:
        return username
    return f"{display} ({username})"


class GroupMemberUserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return group_member_user_label(obj)


@admin.register(models.GroupCategory)
class GroupCategoryAdmin(TranslationAdmin):
    list_display = (
        "name",
        "slug",
    )
    readonly_fields = ("slug",)


class GroupMemberInline(admin.TabularInline):
    model = models.GroupMember

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "user":
            kwargs["form_class"] = GroupMemberUserChoiceField
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class GroupProfileAdmin(admin.ModelAdmin):
    inlines = [GroupMemberInline]
    exclude = [
        "group",
    ]
    actions = [set_user_and_group_dataset_permission]


admin.site.register(models.GroupProfile, GroupProfileAdmin)
