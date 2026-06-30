from urllib.parse import urlparse

from rest_framework import serializers

from geonode.zalf.models import HighlightedCase, SpotlightBanner, TrainingResource
from geonode.zalf.api.cms_utils import render_markdown

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

SAFE_SCHEMES = ('http', 'https', '')


def _validate_href(value):
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme not in SAFE_SCHEMES:
        raise serializers.ValidationError(
            "href must be a relative path or an http/https URL."
        )
    return value


def _validate_image(value):
    if value and hasattr(value, 'size') and value.size > MAX_IMAGE_BYTES:
        raise serializers.ValidationError("Image must be under 5 MB.")
    return value


class HighlightedCaseListSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = HighlightedCase
        fields = [
            'id', 'tab_label', 'eyebrow', 'title', 'button_text',
            'href', 'image_url', 'slug', 'order', 'is_active',
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class HighlightedCaseDetailSerializer(HighlightedCaseListSerializer):
    body_html = serializers.SerializerMethodField()

    class Meta(HighlightedCaseListSerializer.Meta):
        fields = HighlightedCaseListSerializer.Meta.fields + ['body_markdown', 'body_html']

    def get_body_html(self, obj):
        return render_markdown(obj.body_markdown)


class HighlightedCaseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = HighlightedCase
        fields = [
            'id', 'tab_label', 'eyebrow', 'title', 'button_text',
            'href', 'image', 'body_markdown', 'slug', 'order', 'is_active',
        ]
        extra_kwargs = {'slug': {'required': False}}

    def validate_href(self, value):
        return _validate_href(value)

    def validate_image(self, value):
        return _validate_image(value)


class SpotlightBannerSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = SpotlightBanner
        fields = [
            'id', 'kicker', 'title', 'description', 'button_text',
            'href', 'image_url', 'order', 'is_active',
        ]

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class SpotlightBannerWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpotlightBanner
        fields = [
            'id', 'kicker', 'title', 'description', 'button_text',
            'href', 'image', 'order', 'is_active',
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
            'id', 'title', 'organizer', 'category', 'format', 'duration',
            'start_date', 'end_date', 'course_url',
            'thumbnail_url', 'slug', 'order', 'is_active',
        ]

    def get_thumbnail_url(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None


class TrainingResourceDetailSerializer(TrainingResourceListSerializer):
    body_html = serializers.SerializerMethodField()

    class Meta(TrainingResourceListSerializer.Meta):
        fields = TrainingResourceListSerializer.Meta.fields + ['body_markdown', 'body_html']

    def get_body_html(self, obj):
        return render_markdown(obj.body_markdown)


class TrainingResourceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingResource
        fields = [
            'id', 'title', 'organizer', 'category', 'format', 'duration',
            'start_date', 'end_date', 'course_url',
            'thumbnail', 'body_markdown', 'slug', 'order', 'is_active',
        ]
        extra_kwargs = {'slug': {'required': False}}

    def validate_thumbnail(self, value):
        return _validate_image(value)
