from rest_framework import generics

from geonode.zalf_cms.api.serializers import (
    BannerSerializer,
    HighlightCaseSerializer,
    NewsPageSerializer,
    TrainingPageSerializer,
)
from geonode.zalf_cms.models import Banner, HighlightCase, NewsPage, TrainingPage


class BannerListView(generics.ListAPIView):
    serializer_class = BannerSerializer

    def get_queryset(self):
        return Banner.objects.filter(is_active=True).order_by("order", "title")


class HighlightCaseListView(generics.ListAPIView):
    serializer_class = HighlightCaseSerializer

    def get_queryset(self):
        return HighlightCase.objects.filter(is_active=True).order_by("order", "title")


class TrainingPageListView(generics.ListAPIView):
    serializer_class = TrainingPageSerializer

    def get_queryset(self):
        queryset = TrainingPage.objects.live().public().order_by("title")
        is_featured = self.request.query_params.get("is_featured")
        if is_featured in {"1", "true", "True"}:
            queryset = queryset.filter(is_featured=True)
        return queryset


class TrainingPageDetailView(generics.RetrieveAPIView):
    serializer_class = TrainingPageSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return TrainingPage.objects.live().public()


class NewsPageListView(generics.ListAPIView):
    serializer_class = NewsPageSerializer

    def get_queryset(self):
        return NewsPage.objects.live().public().order_by("-published_at", "-first_published_at", "title")


class NewsPageDetailView(generics.RetrieveAPIView):
    serializer_class = NewsPageSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return NewsPage.objects.live().public()
