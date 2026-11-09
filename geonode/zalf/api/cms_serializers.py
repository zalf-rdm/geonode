import json
from urllib.parse import urlparse

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import translation

from rest_framework import serializers

from geonode.zalf.models import (
    HighlightedCase,
    HomepageSection,
    SpotlightBanner,
    Topic,
    TrainingResource,
    translated_field_names,
)
from geonode.zalf.api.cms_utils import render_markdown
from geonode.zalf.api.topic_filters import validate_filter_spec

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

SAFE_SCHEMES = ("http", "https", "")


def _validate_href(value):
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme not in SAFE_SCHEMES:
        raise serializers.ValidationError("href must be a relative path or an http/https URL.")
    return value


def _validate_image(value):
    if value and hasattr(value, "size") and value.size > MAX_IMAGE_BYTES:
        raise serializers.ValidationError("Image must be under 5 MB.")
    return value


class HighlightedCaseListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = HighlightedCase
        fields = [
            "id",
            "tab_label",
            "eyebrow",
            "title",
            "button_text",
            "href",
            "image_url",
            "slug",
            "order",
            "is_active",
            # Raw per-locale variants: the client resolves them against MapStore's
            # live locale, as it does for Topic names (see TopicSerializer).
            *translated_field_names("tab_label", "eyebrow", "title", "button_text"),
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class HighlightedCaseDetailSerializer(HighlightedCaseListSerializer):
    body_html = serializers.SerializerMethodField()

    class Meta(HighlightedCaseListSerializer.Meta):
        fields = HighlightedCaseListSerializer.Meta.fields + [
            "body_markdown",
            *translated_field_names("body_markdown"),
            "body_html",
        ]

    def get_body_html(self, obj):
        # Rendered for Django's active language.
        return render_markdown(obj.localized("body_markdown"))


class HighlightedCaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = HighlightedCase
        fields = [
            "id",
            "tab_label",
            "eyebrow",
            "title",
            "button_text",
            "href",
            "image",
            "body_markdown",
            "slug",
            "order",
            "is_active",
            *translated_field_names(*HighlightedCase.TRANSLATED_FIELDS),
        ]
        extra_kwargs = {"slug": {"required": False}}

    def validate_href(self, value):
        return _validate_href(value)

    def validate_image(self, value):
        return _validate_image(value)


class SpotlightBannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = SpotlightBanner
        fields = [
            "id",
            "kicker",
            "title",
            "description",
            "button_text",
            "href",
            "image_url",
            "order",
            "is_active",
            *translated_field_names(*SpotlightBanner.TRANSLATED_FIELDS),
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class SpotlightBannerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpotlightBanner
        fields = [
            "id",
            "kicker",
            "title",
            "description",
            "button_text",
            "href",
            "image",
            "order",
            "is_active",
            *translated_field_names(*SpotlightBanner.TRANSLATED_FIELDS),
        ]

    def validate_href(self, value):
        return _validate_href(value)

    def validate_image(self, value):
        return _validate_image(value)


class TrainingResourceListSerializer(serializers.ModelSerializer):
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = TrainingResource
        fields = [
            "id",
            "title",
            "organizer",
            "category",
            "format",
            "duration",
            "start_date",
            "end_date",
            "course_url",
            "thumbnail_url",
            "slug",
            "order",
            "is_active",
            *translated_field_names("title", "category", "duration"),
        ]

    def get_thumbnail_url(self, obj):
        if obj.thumbnail:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None


class TrainingResourceDetailSerializer(TrainingResourceListSerializer):
    body_html = serializers.SerializerMethodField()

    class Meta(TrainingResourceListSerializer.Meta):
        fields = TrainingResourceListSerializer.Meta.fields + [
            "body_markdown",
            *translated_field_names("body_markdown"),
            "body_html",
        ]

    def get_body_html(self, obj):
        # Rendered for Django's active language.
        return render_markdown(obj.localized("body_markdown"))


class TrainingResourceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingResource
        fields = [
            "id",
            "title",
            "organizer",
            "category",
            "format",
            "duration",
            "start_date",
            "end_date",
            "course_url",
            "thumbnail",
            "body_markdown",
            "slug",
            "order",
            "is_active",
            *translated_field_names(*TrainingResource.TRANSLATED_FIELDS),
        ]
        extra_kwargs = {"slug": {"required": False}}

    def validate_thumbnail(self, value):
        return _validate_image(value)


class TopicFilterSpecField(serializers.JSONField):
    """
    Accepts a JSON list, or a JSON *string*.

    The string branch is required, not defensive: the CMS editor posts multipart
    (topics carry an image) and cmsApi.buildFormData does String(v) on every
    value, so an array would arrive as "[object Object]". The editor sends
    JSON.stringify(filters) and this field parses it back.
    """

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data or "[]")
            except ValueError:
                raise serializers.ValidationError("filters must be valid JSON.")
        try:
            return validate_filter_spec(data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages)


class TopicSerializer(serializers.ModelSerializer):
    """
    Read serializer.

    Carries both the resolved label (`name_localized`, for non-React consumers)
    and the raw per-locale fields. The homepage resolves the label client-side
    from the raw fields, because MapStore's locale is switched without a page
    reload and can diverge from Django's Accept-Language-derived language.
    """

    image_url = serializers.SerializerMethodField()
    name_localized = serializers.SerializerMethodField()
    catalogue_href = serializers.ReadOnlyField()

    class Meta:
        model = Topic
        fields = [
            "id",
            "slug",
            "name",
            "name_localized",
            "name_de",
            "name_fr",
            "name_es",
            "name_it",
            "search_term",
            "filters",
            "catalogue_href",
            "image_url",
            "icon",
            "show_in_navbar",
            "show_on_homepage",
            "order",
            "is_active",
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_name_localized(self, obj):
        request = self.context.get("request")
        # `?lang=` for parity with the facets API; otherwise the active language.
        lang = (request.GET.get("lang") if request else None) or translation.get_language()
        return obj.localized_name(lang)


class TopicWriteSerializer(serializers.ModelSerializer):
    filters = TopicFilterSpecField(required=False)

    class Meta:
        model = Topic
        fields = [
            "id",
            "name",
            "name_de",
            "name_fr",
            "name_es",
            "name_it",
            "slug",
            "search_term",
            "filters",
            "image",
            "icon",
            "show_in_navbar",
            "show_on_homepage",
            "order",
            "is_active",
        ]
        extra_kwargs = {"slug": {"required": False}}

    def validate_image(self, value):
        return _validate_image(value)

    def validate(self, attrs):
        # A topic with neither a search term nor a filter links to the bare
        # catalogue, which is never what the admin meant.
        instance = self.instance
        term = attrs.get("search_term", getattr(instance, "search_term", "") or "")
        rows = attrs.get("filters", getattr(instance, "filters", []) or [])
        if not term and not rows:
            raise serializers.ValidationError("A topic needs at least one filter or a search term.")
        return attrs


class HomepageSectionSerializer(serializers.ModelSerializer):
    label = serializers.ReadOnlyField()

    class Meta:
        model = HomepageSection
        fields = ["id", "key", "label", "order", "is_active"]
        # The row set is fixed and seeded by migration, so `key` identifies a
        # section rather than being something the CMS may change.
        read_only_fields = ["key"]
