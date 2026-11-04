"""Data for the manuscript-location word cloud on the Manuscripts page.

Library records only store a city name, so coordinates for each holding city
live here. The cloud uses them only to keep cities in the right compass
order (north/south/east/west); a city that isn't listed still appears in the
panel under "Location not mapped" and is logged so it can be added.
"""

import logging
import re
import unicodedata

from django.urls import reverse

logger = logging.getLogger(__name__)

# key: normalized city name -> (display name, country, lat, lon)
CITY_COORDS = {
    "amsterdam": ("Amsterdam", "Netherlands", 52.372, 4.894),
    "basel": ("Basel", "Switzerland", 47.559, 7.588),
    "bergamo": ("Bergamo", "Italy", 45.698, 9.677),
    "bologna": ("Bologna", "Italy", 44.494, 11.343),
    "boston": ("Boston", "USA", 42.350, -71.078),
    "brussels": ("Brussels", "Belgium", 50.850, 4.352),
    "cambridge ma": ("Cambridge, MA", "USA", 42.374, -71.116),
    "chicago": ("Chicago", "USA", 41.878, -87.630),
    "cortona": ("Cortona", "Italy", 43.275, 11.985),
    "florence": ("Florence", "Italy", 43.773, 11.256),
    "forli": ("Forlì", "Italy", 44.222, 12.041),
    "genoa": ("Genoa", "Italy", 44.405, 8.946),
    "gubbio": ("Gubbio", "Italy", 43.352, 12.577),
    "helsinki": ("Helsinki", "Finland", 60.170, 24.938),
    "ithaca ny": ("Ithaca, NY", "USA", 42.448, -76.484),
    "krakow": ("Krakow", "Poland", 50.065, 19.945),
    "warsaw": ("Warsaw", "Poland", 52.230, 21.011),
    "lawrence ks": ("Lawrence, KS", "USA", 38.958, -95.247),
    "london": ("London", "UK", 51.520, -0.127),
    "lucca": ("Lucca", "Italy", 43.843, 10.505),
    "milan": ("Milan", "Italy", 45.464, 9.190),
    "modena": ("Modena", "Italy", 44.647, 10.925),
    "naples": ("Naples", "Italy", 40.852, 14.268),
    "new haven": ("New Haven", "USA", 41.311, -72.926),
    "new york": ("New York", "USA", 40.753, -73.982),
    "oxford": ("Oxford", "UK", 51.754, -1.254),
    "padua": ("Padua", "Italy", 45.406, 11.877),
    "paris": ("Paris", "France", 48.857, 2.352),
    "parma": ("Parma", "Italy", 44.801, 10.328),
    "pavia": ("Pavia", "Italy", 45.185, 9.159),
    "perugia": ("Perugia", "Italy", 43.112, 12.389),
    "poppi": ("Poppi", "Italy", 43.721, 11.763),
    "pesaro": ("Pesaro", "Italy", 43.910, 12.913),
    "prato": ("Prato", "Italy", 43.878, 11.102),
    "ravenna": ("Ravenna", "Italy", 44.418, 12.204),
    "rome": ("Rome", "Italy", 41.900, 12.483),
    "siena": ("Siena", "Italy", 43.318, 11.331),
    "tenri": ("Tenri, Japan", "Japan", 34.597, 135.837),
    "tenri japan": ("Tenri, Japan", "Japan", 34.597, 135.837),
    "treviso": ("Treviso", "Italy", 45.666, 12.245),
    "turin": ("Turin", "Italy", 45.070, 7.687),
    "vaduz": ("Vaduz", "Liechtenstein", 47.141, 9.521),
    "vatican city": ("Vatican City", "Vatican City", 41.904, 12.454),
    "venice": ("Venice", "Italy", 45.434, 12.338),
    "vicenza": ("Vicenza", "Italy", 45.546, 11.535),
    "vienna": ("Vienna", "Austria", 48.206, 16.367),
    "volterra": ("Volterra", "Italy", 43.402, 10.861),
    "washington dc": ("Washington DC", "USA", 38.889, -77.005),
}

# City values that mean "we don't know where it is"
UNLOCATED = {"", "unknown", "unverified", "irrelevant"}


def normalize_city(name):
    """'Cambridge, MA' / 'Cambridge MA' / 'Forlì' -> 'cambridge ma' / 'forli'"""
    name = unicodedata.normalize("NFKD", name or "")
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^\w\s]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def build_cloud_places(manuscripts, library_id_map):
    """Group manuscripts by holding city, then by library.

    `manuscripts` and `library_id_map` are the structures already built in
    `views.manuscripts`. Returns a list of dicts ready for `json_script`.
    """
    places = {}
    for ms in manuscripts:
        if not ms.get("siglum"):
            continue
        library = library_id_map.get(ms.get("library")) or {}
        key = normalize_city(library.get("city"))
        coords = CITY_COORDS.get(key)
        if coords:
            label, country, lat, lon = coords
        else:
            if key not in UNLOCATED:
                logger.info(
                    "Manuscript cloud: no coordinates for city %r", library.get("city")
                )
            label, country, lat, lon = "Location not mapped", "", None, None
        place = places.setdefault(
            label,
            {"city": label, "country": country, "lat": lat, "lon": lon, "inst": {}},
        )
        inst_name = library.get("library") or "Unknown library"
        place["inst"].setdefault(inst_name, []).append(
            [
                ms.get("shelfmark") or "no shelfmark",
                ms["siglum"],
                reverse("manuscript", args=[ms["siglum"]]),
            ]
        )

    return [
        {**p, "inst": [{"name": k, "mss": v} for k, v in p["inst"].items()]}
        for p in places.values()
    ]
