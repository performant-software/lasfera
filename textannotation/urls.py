from django.urls import path

from manuscript import views

app_name = "textannotation"

urlpatterns = [
    path(
        "get/<int:stanza_id>/",
        views.get_annotations,
        name="get_annotations",
    ),
    path(
        "annotation/<str:annotation_type>/<int:annotation_id>/",
        views.get_annotation,
        name="get_annotation",
    ),
]
