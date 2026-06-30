from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from oauth2_provider.contrib.rest_framework import OAuth2Authentication

from geonode.zalf.models import HighlightedCase, SpotlightBanner, TrainingResource
from geonode.zalf.api.cms_serializers import (
    HighlightedCaseListSerializer,
    HighlightedCaseDetailSerializer,
    HighlightedCaseWriteSerializer,
    SpotlightBannerSerializer,
    SpotlightBannerWriteSerializer,
    TrainingResourceListSerializer,
    TrainingResourceDetailSerializer,
    TrainingResourceWriteSerializer,
)
from geonode.zalf.api.cms_utils import render_markdown

AUTH_CLASSES = [SessionAuthentication, BasicAuthentication, OAuth2Authentication]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _staff_required(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
    if not request.user.is_staff:
        return Response({"detail": "Staff access required."}, status=status.HTTP_403_FORBIDDEN)
    return None


# ---------------------------------------------------------------------------
# Highlighted Cases
# ---------------------------------------------------------------------------


class HighlightedCaseListCreateView(APIView):
    authentication_classes = AUTH_CLASSES

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]

    def get(self, request):
        qs = HighlightedCase.objects.all() if request.user.is_staff else HighlightedCase.objects.filter(is_active=True)
        return Response(HighlightedCaseListSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = HighlightedCaseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            HighlightedCaseListSerializer(obj, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class HighlightedCaseDetailView(APIView):
    authentication_classes = AUTH_CLASSES

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]

    def _get_object(self, pk_or_slug):
        try:
            return HighlightedCase.objects.get(pk=int(pk_or_slug))
        except (ValueError, HighlightedCase.DoesNotExist):
            return get_object_or_404(HighlightedCase, slug=pk_or_slug)

    def get(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        return Response(HighlightedCaseDetailSerializer(obj, context={"request": request}).data)

    def put(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        serializer = HighlightedCaseWriteSerializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(HighlightedCaseListSerializer(obj, context={"request": request}).data)

    def patch(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        serializer = HighlightedCaseWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(HighlightedCaseListSerializer(obj, context={"request": request}).data)

    def delete(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Spotlight Banners
# ---------------------------------------------------------------------------


class SpotlightBannerListCreateView(APIView):
    authentication_classes = AUTH_CLASSES

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]

    def get(self, request):
        qs = SpotlightBanner.objects.all() if request.user.is_staff else SpotlightBanner.objects.filter(is_active=True)
        return Response(SpotlightBannerSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = SpotlightBannerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            SpotlightBannerSerializer(obj, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class SpotlightBannerDetailView(APIView):
    authentication_classes = AUTH_CLASSES

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]

    def get(self, request, pk):
        obj = get_object_or_404(SpotlightBanner, pk=pk)
        return Response(SpotlightBannerSerializer(obj, context={"request": request}).data)

    def put(self, request, pk):
        obj = get_object_or_404(SpotlightBanner, pk=pk)
        serializer = SpotlightBannerWriteSerializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(SpotlightBannerSerializer(obj, context={"request": request}).data)

    def patch(self, request, pk):
        obj = get_object_or_404(SpotlightBanner, pk=pk)
        serializer = SpotlightBannerWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(SpotlightBannerSerializer(obj, context={"request": request}).data)

    def delete(self, request, pk):
        obj = get_object_or_404(SpotlightBanner, pk=pk)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Training Resources
# ---------------------------------------------------------------------------


class TrainingResourceListCreateView(APIView):
    authentication_classes = AUTH_CLASSES

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]

    def get(self, request):
        qs = (
            TrainingResource.objects.all() if request.user.is_staff else TrainingResource.objects.filter(is_active=True)
        )
        return Response(TrainingResourceListSerializer(qs, many=True, context={"request": request}).data)

    def post(self, request):
        serializer = TrainingResourceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            TrainingResourceListSerializer(obj, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TrainingResourceDetailView(APIView):
    authentication_classes = AUTH_CLASSES

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsAdminUser()]

    def _get_object(self, pk_or_slug):
        try:
            return TrainingResource.objects.get(pk=int(pk_or_slug))
        except (ValueError, TrainingResource.DoesNotExist):
            return get_object_or_404(TrainingResource, slug=pk_or_slug)

    def get(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        return Response(TrainingResourceDetailSerializer(obj, context={"request": request}).data)

    def put(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        serializer = TrainingResourceWriteSerializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(TrainingResourceListSerializer(obj, context={"request": request}).data)

    def patch(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        serializer = TrainingResourceWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(TrainingResourceListSerializer(obj, context={"request": request}).data)

    def delete(self, request, pk_or_slug):
        obj = self._get_object(pk_or_slug)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Markdown preview (staff only)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@authentication_classes(AUTH_CLASSES)
@permission_classes([IsAuthenticated, IsAdminUser])
def preview_markdown(request):
    text = request.data.get("text", "")
    if not isinstance(text, str):
        return Response({"detail": "text must be a string."}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"html": render_markdown(text)})
