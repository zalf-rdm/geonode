from django.contrib import admin
from django.db import models as django_models

from geonode.assets.admin import PrettyJSONWidget

from .models import DownloadPackage, HighlightedCase, HomepageSection, SpotlightBanner, Topic, TrainingResource


@admin.register(HighlightedCase)
class HighlightedCaseAdmin(admin.ModelAdmin):
    list_display = ("tab_label", "title", "order", "is_active")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"slug": ("tab_label",)}
    search_fields = ("tab_label", "title")
    ordering = ("order",)


@admin.register(SpotlightBanner)
class SpotlightBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "kicker", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("title", "kicker")
    ordering = ("order",)


@admin.register(TrainingResource)
class TrainingResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "organizer", "order", "is_active")
    list_editable = ("order", "is_active")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "organizer")
    ordering = ("order",)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active", "show_in_navbar", "show_on_homepage", "catalogue_href")
    list_editable = ("order", "is_active", "show_in_navbar", "show_on_homepage")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "name_de", "name_fr", "name_es", "name_it", "search_term")
    ordering = ("order",)
    # The real editing surface is the React CMS; this is the escape hatch, so the
    # filter spec is edited as pretty-printed JSON. Topic.clean() validates it,
    # and ModelAdmin calls full_clean(), so a bad spec shows as a form error.
    formfield_overrides = {django_models.JSONField: {"widget": PrettyJSONWidget}}
    fieldsets = (
        (None, {"fields": ("name", "slug", "order", "is_active")}),
        ("Translations", {"fields": ("name_de", "name_fr", "name_es", "name_it")}),
        ("Catalogue link", {"fields": ("search_term", "filters")}),
        ("Presentation", {"fields": ("image", "icon", "show_in_navbar", "show_on_homepage")}),
    )


@admin.register(HomepageSection)
class HomepageSectionAdmin(admin.ModelAdmin):
    list_display = ("key", "order", "is_active")
    list_editable = ("order", "is_active")
    ordering = ("order",)
    # Fixed, migration-seeded row set: reorder and hide only.
    readonly_fields = ("key",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DownloadPackage)
class DownloadPackageAdmin(admin.ModelAdmin):
    list_display = ("map", "state", "size", "built_at", "updated_at")
    list_filter = ("state",)
    search_fields = ("map__title",)
    readonly_fields = (
        "map",
        "state",
        "asset",
        "task_id",
        "error",
        "size",
        "sha256",
        "built_at",
        "requested_by",
        "updated_at",
    )
    actions = ["rebuild"]

    def has_add_permission(self, request):
        # Packages are created by building one: the publish workflow, the map's
        # download_package endpoint or the build_download_packages command.
        return False

    @admin.action(description="Rebuild the download package")
    def rebuild(self, request, queryset):
        from geonode.zalf.download_packages import request_build

        started = sum(request_build(package.map, user=request.user)[1] for package in queryset.select_related("map"))
        self.message_user(request, f"Queued {started} of {queryset.count()} builds; the others are already running.")
