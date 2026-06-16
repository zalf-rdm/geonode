from django.urls import path

from geonode.zalf_cms.api.views import (
    BannerListView,
    HighlightCaseListView,
    NewsPageDetailView,
    NewsPageListView,
    TrainingPageDetailView,
    TrainingPageListView,
    ZalfCmsRootView,
)

urlpatterns = [
    path("", ZalfCmsRootView.as_view(), name="zalf-cms-root"),
    path("banners/", BannerListView.as_view(), name="zalf-cms-banners"),
    path("highlight-cases/", HighlightCaseListView.as_view(), name="zalf-cms-highlight-cases"),
    path("trainings/", TrainingPageListView.as_view(), name="zalf-cms-trainings"),
    path("trainings/<slug:slug>/", TrainingPageDetailView.as_view(), name="zalf-cms-training-detail"),
    path("news/", NewsPageListView.as_view(), name="zalf-cms-news"),
    path("news/<slug:slug>/", NewsPageDetailView.as_view(), name="zalf-cms-news-detail"),
]
