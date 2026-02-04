from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls

from manuscript.views import about, data, education, talks

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
    path("about/", about, name="about"),
    path("resources/education/", education, name="education"),
    path("resources/data/", data, name="data"),
    path("resources/talks-presentations/", talks, name="talks"),
    path("gallery/", include("gallery.urls", namespace="gallery")),
    path("cms/", include(wagtailadmin_urls)),
    path("pages/", include(wagtail_urls)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls"))]
