from django.contrib import admin
from .models import HighlightedCase, SpotlightBanner, TrainingResource


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
