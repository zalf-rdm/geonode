from rest_framework import serializers
from rest_framework.reverse import reverse

from geonode.zalf_cms.models import Banner, HighlightCase, NewsPage, TrainingPage


def image_url(image):
    if not image:
        return None
    try:
        request = getattr(image, "_serializer_request", None)
        url = image.file.url
        if request:
            return request.build_absolute_uri(url)
        return url
    except ValueError:
        return None


def streamfield_value(value):
    if not value:
        return []
    return value.get_prep_value()


def page_url(obj, request, detail_route_name):
    public_url = obj.get_url(request=request)
    if public_url:
        return public_url
    return reverse(detail_route_name, kwargs={"slug": obj.slug}, request=request)


def linked_page_url(page, request):
    if not page:
        return ""

    specific = page.specific
    if isinstance(specific, TrainingPage):
        return page_url(specific, request, "zalf-cms-training-detail")
    if isinstance(specific, NewsPage):
        return page_url(specific, request, "zalf-cms-news-detail")

    public_url = specific.get_url(request=request)
    return public_url or ""


class BannerSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = ("id", "eyebrow", "title", "subtitle", "image", "link", "url", "button_label", "order")

    def get_image(self, obj):
        if obj.image:
            obj.image._serializer_request = self.context.get("request")
        return image_url(obj.image)

    def get_url(self, obj):
        request = self.context.get("request")
        return linked_page_url(obj.target_page, request) or obj.link


class HighlightCaseSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = HighlightCase
        fields = ("id", "title", "subtitle", "description", "image", "link", "button_text", "order")

    def get_image(self, obj):
        if obj.image:
            obj.image._serializer_request = self.context.get("request")
        return image_url(obj.image)


class TrainingPageSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(read_only=True)
    hero_image = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

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
            "url",
            "level",
            "duration",
            "source",
            "external_link",
            "is_featured",
        )

    def get_hero_image(self, obj):
        if obj.hero_image:
            obj.hero_image._serializer_request = self.context.get("request")
        return image_url(obj.hero_image)

    def get_body(self, obj):
        return streamfield_value(obj.body)

    def get_url(self, obj):
        request = self.context.get("request")
        return page_url(obj, request, "zalf-cms-training-detail")


class NewsPageSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(read_only=True)
    hero_image = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    url = serializers.SerializerMethodField()

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
            "url",
            "published_at",
            "tags",
            "external_link",
            "is_featured",
        )

    def get_hero_image(self, obj):
        if obj.hero_image:
            obj.hero_image._serializer_request = self.context.get("request")
        return image_url(obj.hero_image)

    def get_body(self, obj):
        return streamfield_value(obj.body)

    def get_url(self, obj):
        request = self.context.get("request")
        return page_url(obj, request, "zalf-cms-news-detail")
