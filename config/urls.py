from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls

urlpatterns = [
    path("", include("manuscript.urls")),
    path(
        "text-annotations/", include("textannotation.urls", namespace="textannotation")
    ),
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
    path("toponyms/", include(("manuscript.urls", "toponyms"), namespace="toponyms")),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("prose/", include("prose.urls")),
    path("gallery/", include("gallery.urls", namespace="gallery")),
    path("cms/", include(wagtailadmin_urls)),
]

if settings.DEBUG:
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls"))]

urlpatterns += [
    path("", include(wagtail_urls)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
