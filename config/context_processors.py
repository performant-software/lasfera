from django.conf import settings


def carto(request):
    """Expose the CARTO API key to templates for the gazetteer basemaps."""
    return {"CARTO_API_KEY": settings.CARTO_API_KEY}
