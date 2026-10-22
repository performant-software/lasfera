from django.conf import settings


def carto(request):
    """Expose the CARTO API key to templates for the gazetteer basemaps."""
    return {"CARTO_API_KEY": settings.CARTO_API_KEY}


def test_site_banner(request):
    """Whether to show the test site banner, on the site and in the admin."""
    return {"TEST_SITE_BANNER": settings.TEST_SITE_BANNER}
