from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from geonode.zalf_cms.api.serializers import (
    BannerSerializer,
    HighlightCaseSerializer,
    NewsPageSerializer,
    TrainingPageSerializer,
)
from geonode.zalf_cms.models import Banner, HighlightCase, NewsPage, TrainingPage


class ZalfCmsRootView(APIView):
    def get(self, request):
        base_url = request.build_absolute_uri()
        if not base_url.endswith("/"):
            base_url = f"{base_url}/"

        return Response(
            {
                "banners": f"{base_url}banners/",
                "highlight_cases": f"{base_url}highlight-cases/",
                "trainings": f"{base_url}trainings/",
                "news": f"{base_url}news/",
            }
        )


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
        queryset = TrainingPage.objects.live().public().order_by("path")
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
        queryset = NewsPage.objects.live().public().order_by("-published_at", "-first_published_at", "title")
        is_featured = self.request.query_params.get("is_featured")
        if is_featured in {"1", "true", "True"}:
            queryset = queryset.filter(is_featured=True)
        return queryset


class NewsPageDetailView(generics.RetrieveAPIView):
    serializer_class = NewsPageSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return NewsPage.objects.live().public()
