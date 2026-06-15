from rest_framework import serializers

from geonode.zalf_cms.models import Banner, HighlightCase, NewsPage, TrainingPage


def image_url(image):
    if not image:
        return None
    try:
        return image.file.url
    except ValueError:
        return None


def streamfield_value(value):
    if not value:
        return []
    return value.get_prep_value()


class BannerSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = ("id", "title", "subtitle", "image", "link", "order")

    def get_image(self, obj):
        return image_url(obj.image)


class HighlightCaseSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = HighlightCase
        fields = ("id", "title", "subtitle", "description", "image", "link", "button_text", "order")

    def get_image(self, obj):
        return image_url(obj.image)


class TrainingPageSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(read_only=True)
    hero_image = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()

    class Meta:
        model = TrainingPage
        fields = (
            "id",
            "title",
            "slug",
            "subtitle",
            "summary",
            "hero_image",
            "body",
            "level",
            "duration",
            "source",
            "external_link",
            "is_featured",
        )

    def get_hero_image(self, obj):
        return image_url(obj.hero_image)

    def get_body(self, obj):
        return streamfield_value(obj.body)


class NewsPageSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(read_only=True)
    hero_image = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()

    class Meta:
        model = NewsPage
        fields = (
            "id",
            "title",
            "slug",
            "subtitle",
            "summary",
            "hero_image",
            "body",
            "published_at",
            "tags",
        )

    def get_hero_image(self, obj):
        return image_url(obj.hero_image)

    def get_body(self, obj):
        return streamfield_value(obj.body)
