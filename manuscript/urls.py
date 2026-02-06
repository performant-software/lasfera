from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"toponyms", views.ToponymViewSet, basename="toponyms")
router.register(r"toponym-detail", views.ToponymViewSet, basename="toponym-detail")
router.register(
    r"manuscript-detail", views.SingleManuscriptViewSet, basename="manuscript-detail"
)
urlpatterns = [
    # Core pages
    path("", views.index, name="index"),
    # Manuscript routes
    path("manuscripts/", views.manuscripts, name="manuscripts"),
    path("manuscripts/<str:siglum>/", views.manuscript, name="manuscript"),
    path(
        "manuscripts/<str:siglum>/stanzas/",
        views.manuscript_stanzas,
        name="manuscript_stanzas",
    ),
    # Toponym routes
    path("toponyms/", views.toponyms, name="toponyms"),
    path("toponyms/<slug:toponym_slug>/", views.toponym_by_slug, name="toponym_detail"),
    path("toponym-search/", views.search_toponyms, name="search_toponyms"),
    # API and annotations
    path("api/", include(router.urls)),
    path("text-annotations/create/", views.create_annotation, name="create_annotation"),
]
