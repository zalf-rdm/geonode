from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models as django_models
from django.template.response import TemplateResponse
from django.urls import path

from geonode.assets.admin import PrettyJSONWidget

from .models import (
    DownloadPackage,
    HighlightedCase,
    HomepageSection,
    S3Asset,
    SpotlightBanner,
    Topic,
    TrainingResource,
)


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
    actions = ["rebuild", "validate"]
    # Adds the "Validate storage" button next to the changelist's own tools.
    change_list_template = "zalf/admin/download_package_change_list.html"

    def has_add_permission(self, request):
        # Packages are created by building one: the publish workflow, the map's
        # download_package endpoint or the build_download_packages command.
        return False

    # -- Validation ---------------------------------------------------------
    #
    # A row says what the last build concluded; only the storage can say whether
    # the file is still there. The checks live in download_package_checks, shared
    # with `manage.py download_package_status`, so the two cannot disagree.
    #
    # Nothing here runs on the changelist itself: one HEAD request per row would
    # make the list as slow as the bucket is far away, and unusable when the
    # bucket is unreachable. Validation happens only when asked for.

    def get_urls(self):
        own = [
            path(
                "validation/",
                self.admin_site.admin_view(self.validation_view),
                name="zalf_downloadpackage_validation",
            )
        ]
        return own + super().get_urls()

    @admin.action(description="Validate the stored package")
    def validate(self, request, queryset):
        from geonode.zalf import download_package_checks

        results = download_package_checks.check_packages(packages=queryset)
        for result in results:
            level = messages.SUCCESS if result.is_ok else messages.ERROR if result.is_broken else messages.WARNING
            self.message_user(
                request, f"Map {result.map_id} ({result.map_title}): {result.status} -- {result.detail}", level=level
            )

    def validation_view(self, request):
        """The report page: every package checked against its storage."""
        from geonode.zalf import download_package_checks
        from geonode.zalf.download_packages import is_enabled
        from geonode.zalf.s3_assets import s3_configured

        if not self.has_view_permission(request):
            raise PermissionDenied
        deep = request.GET.get("deep") == "1"
        show_orphans = request.GET.get("orphans") == "1"

        results = download_package_checks.check_packages(include_missing=True, deep=deep)
        counts = download_package_checks.summarize(results)
        broken = sum(count for status, count in counts.items() if status in download_package_checks.BROKEN)

        orphans, truncated, orphan_error, dangling = [], False, "", []
        if show_orphans:
            try:
                orphans, truncated = download_package_checks.find_orphans()
                dangling = download_package_checks.find_dangling_assets()
            except RuntimeError as error:
                orphan_error = str(error)

        context = {
            **self.admin_site.each_context(request),
            "title": "Download package validation",
            "opts": self.model._meta,
            "results": results,
            "counts": counts,
            "broken": broken,
            "broken_statuses": sorted(download_package_checks.BROKEN),
            "deep": deep,
            "show_orphans": show_orphans,
            "orphans": orphans,
            "orphans_truncated": truncated,
            "orphan_error": orphan_error,
            "dangling": dangling,
            "feature_enabled": is_enabled(),
            "s3_configured": s3_configured(),
        }
        return TemplateResponse(request, "zalf/admin/download_package_validation.html", context)

    @admin.action(description="Rebuild the download package")
    def rebuild(self, request, queryset):
        from geonode.zalf.download_packages import is_enabled, request_build

        if not is_enabled():
            self.message_user(
                request,
                "Download packages are switched off (ZALF_DOWNLOAD_PACKAGE_ENABLED); nothing was queued.",
                level=messages.WARNING,
            )
            return
        started = sum(request_build(package.map, user=request.user)[1] for package in queryset.select_related("map"))
        self.message_user(request, f"Queued {started} of {queryset.count()} builds; the others are already running.")


@admin.register(S3Asset)
class S3AssetAdmin(admin.ModelAdmin):
    """
    The stored package objects themselves (zalf-rdm/geonode#659).

    GeoNode registers only LocalAsset, so without this an S3Asset could not be
    inspected or removed through the admin at all -- which is where the download
    package validation page sends an operator who has a dangling asset. Deleting
    a row here removes the object from the bucket too, through the handler's
    post_delete.
    """

    list_display = ("id", "title", "type", "bucket", "key", "size", "owner", "created")
    list_display_links = ("id", "title")
    list_filter = ("type", "bucket")
    search_fields = ("key", "title")
    # A row describes a stored object: it is written by a build, not by hand.
    readonly_fields = ("bucket", "key", "size", "sha256", "created")

    def has_add_permission(self, request):
        return False
