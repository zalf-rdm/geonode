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

from django.contrib import admin

from modeltranslation.admin import TabbedTranslationAdmin

from geonode.documents.models import Document
from geonode.base.admin import ResourceBaseAdminForm
from geonode.base.admin import metadata_batch_edit


class DocumentAdminForm(ResourceBaseAdminForm):
    class Meta(ResourceBaseAdminForm.Meta):
        model = Document
        fields = "__all__"
        # exclude = (
        #     'resource',
        # )


class DocumentAdmin(TabbedTranslationAdmin):
    exclude = ("ll_bbox_polygon", "bbox_polygon", "srid")
    list_display = (
        "id",
        "title",
        "date",
        "category",
        "group",
        "is_approved",
        "is_published",
        "advertised",
        "metadata_completeness",
    )
    list_display_links = ("id",)
    list_editable = ("title", "category", "group", "is_approved", "is_published", "advertised")
    list_filter = (
        "date",
        "date_type",
        "restriction_other",
        "category",
        "group",
        "is_approved",
        "is_published",
    )
    search_fields = (
        "title",
        "abstract",
        "purpose",
        "is_approved",
        "is_published",
    )
    readonly_fields = ("geographic_bounding_box",)
    date_hierarchy = "date"
    form = DocumentAdminForm
    actions = [metadata_batch_edit]

    def delete_queryset(self, request, queryset):
        """
        We need to invoke the 'ResourceBase.delete' method even when deleting
        through the admin batch action
        """
        for obj in queryset:
            from geonode.resource.manager import resource_manager

            resource_manager.delete(obj.uuid, instance=obj)


admin.site.register(Document, DocumentAdmin)
