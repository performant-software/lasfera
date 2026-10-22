import re

import requests

FOLIO_LABEL_PREFIX = re.compile(r"^(?:carta|folio|fol|ff|f|c)\s*[.:]?\s*(?=\d)")


def fetch_manifest(manifest_url, timeout=60):
    """Fetch and parse a IIIF manifest"""
    response = requests.get(
        manifest_url, timeout=timeout, headers={"User-Agent": "lasfera"}
    )
    response.raise_for_status()
    return response.json()


def _label_to_str(label):
    """Flatten a IIIF v2 or v3 label into a plain string"""
    if label is None:
        return ""
    if isinstance(label, str):
        return label
    if isinstance(label, list):
        return " ".join(_label_to_str(item) for item in label)
    if isinstance(label, dict):
        if "@value" in label:
            return str(label["@value"])
        # v3 language map, e.g. {"none": ["1r"]}
        return " ".join(_label_to_str(values) for values in label.values())
    return str(label)


def _service_id(service):
    if isinstance(service, list):
        service = service[0] if service else None
    if isinstance(service, dict):
        return service.get("@id") or service.get("id")
    return None


def get_canvases(manifest):
    """Return the canvases of a IIIF v2 or v3 manifest as a list of dicts
    with keys: index (0-based), id, label, image_id"""
    canvases = []
    if "sequences" in manifest:
        raw_canvases = manifest["sequences"][0].get("canvases", [])
    else:
        raw_canvases = manifest.get("items", [])

    for index, canvas in enumerate(raw_canvases):
        image_id = None
        if canvas.get("images"):
            # v2: canvas.images[].resource
            resource = canvas["images"][0].get("resource", {})
            image_id = _service_id(resource.get("service")) or resource.get("@id")
        elif canvas.get("items"):
            # v3: canvas.items[] (annotation pages) .items[] (annotations) .body
            try:
                body = canvas["items"][0]["items"][0]["body"]
                if isinstance(body, list):
                    body = body[0]
                image_id = _service_id(body.get("service")) or body.get("id")
            except (IndexError, KeyError, AttributeError):
                pass

        canvases.append(
            {
                "index": index,
                "id": canvas.get("@id") or canvas.get("id"),
                "label": _label_to_str(canvas.get("label")).strip(),
                "image_id": image_id,
            }
        )
    return canvases


def normalize_folio_label(label):
    """Normalize a folio reference or canvas label for comparison,
    e.g. "Carta: 12 recto", "f. 12r", and "12r" all become "12r"."""
    if not label:
        return ""
    value = label.strip().lower()
    value = re.sub(r"\brecto\b", "r", value)
    value = re.sub(r"\bverso\b", "v", value)
    value = FOLIO_LABEL_PREFIX.sub("", value)
    return re.sub(r"[\s.]", "", value)
