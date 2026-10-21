"""Linking a manuscript's folios to the canvases of its IIIF manifest by hand"""

from collections import Counter, defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction

from manuscript.models import Folio
from manuscript.utils import normalize_folio_label

FOLIO_NUMBER_MAX_LENGTH = Folio._meta.get_field("folio_number").max_length
CANVAS_ID_MAX_LENGTH = Folio._meta.get_field("canvas_id").max_length


def clean_canvas_rows(rows):
    """Validate the rows submitted from the canvas linking page. Each row is a
    canvas from the manifest: id, index, label, image_id, and the folio
    number entered for it (blank for none)."""
    if not isinstance(rows, list):
        raise ValidationError("The submitted images could not be read.")

    cleaned = []
    for row in rows:
        try:
            canvas_id = str(row["id"]).strip()
            index = int(row["index"])
            label = str(row.get("label") or "").strip()[:255]
            image_id = str(row.get("image_id") or "").strip() or None
            folio_number = str(row.get("folio") or "").strip()
        except (KeyError, TypeError, ValueError):
            raise ValidationError("The submitted images could not be read.")
        if not canvas_id or len(canvas_id) > CANVAS_ID_MAX_LENGTH or index < 0:
            raise ValidationError("The submitted images could not be read.")
        if image_id and len(image_id) > CANVAS_ID_MAX_LENGTH:
            image_id = None
        if len(folio_number) > FOLIO_NUMBER_MAX_LENGTH:
            raise ValidationError(
                f"The folio number entered for image {index + 1} is too long."
            )
        cleaned.append(
            {
                "id": canvas_id,
                "index": index,
                "label": label,
                "image_id": image_id,
                "folio": folio_number,
            }
        )

    duplicate_ids = [
        canvas_id
        for canvas_id, count in Counter(row["id"] for row in cleaned).items()
        if count > 1
    ]
    if duplicate_ids:
        raise ValidationError("The manifest lists the same image more than once.")
    return cleaned


def link_canvases(manuscript, rows, can_create=True):
    """Link the manuscript's folios to canvases as entered on the canvas linking
    page, where rows are cleaned by clean_canvas_rows.

    A folio number is matched to an existing folio of the manuscript (ignoring
    differences like "f. 12r" and "12r"), or a new folio is created. Folios are
    never renamed or deleted: a folio whose canvas is cleared or given to
    another folio is only unlinked, so its toponyms and other data stay intact.

    Returns a Counter of linked, unlinked, and created folios, and a list of
    the folios created. Raises ValidationError, without saving anything, if
    the entries conflict."""
    errors = []

    # folio number entered -> row, checking no folio is entered twice
    rows_by_folio = {}
    positions_by_folio = defaultdict(list)
    for row in rows:
        if row["folio"]:
            key = normalize_folio_label(row["folio"]) or row["folio"].lower()
            rows_by_folio[key] = row
            positions_by_folio[key].append(row)
    for key, entered in positions_by_folio.items():
        if len(entered) > 1:
            positions = ", ".join(str(row["index"] + 1) for row in entered)
            errors.append(
                f'Folio "{entered[0]["folio"]}" is entered for more than one '
                f"image ({positions}). Each folio can be linked to one image."
            )

    folios = list(manuscript.folio_set.all())
    folios_by_key = defaultdict(list)
    for folio in folios:
        key = (
            normalize_folio_label(folio.folio_number)
            or (folio.folio_number or "").lower()
        )
        if key:
            folios_by_key[key].append(folio)

    targets = {}  # folio number key -> existing folio, or None to create
    for key, row in rows_by_folio.items():
        matches = folios_by_key.get(key, [])
        if len(matches) > 1:
            numbers = ", ".join(sorted(f'"{f.folio_number}"' for f in matches))
            errors.append(
                f'Folio "{row["folio"]}" matches several folio records in this '
                f"manuscript ({numbers}). Merge or renumber those folio records "
                "first."
            )
        elif matches:
            targets[key] = matches[0]
        elif not can_create:
            errors.append(
                f'There is no folio record "{row["folio"]}" in this manuscript, '
                "and you don't have permission to add folio records."
            )
        else:
            targets[key] = None

    if errors:
        raise ValidationError(errors)

    counts = Counter()
    created = []
    submitted_ids = {row["id"] for row in rows}
    linked_folio_ids = {
        folio.pk: rows_by_folio[key]["id"]
        for key, folio in targets.items()
        if folio is not None
    }
    with transaction.atomic():
        # unlink first, so moving a folio to another canvas can't collide
        # with the one-folio-per-canvas constraint
        for folio in folios:
            if folio.canvas_id not in submitted_ids:
                continue
            if linked_folio_ids.get(folio.pk) == folio.canvas_id:
                continue
            if folio.pk not in linked_folio_ids:
                counts["unlinked"] += 1
            folio.canvas_id = None
            folio.canvas_index = None
            folio.canvas_label = None
            folio.image_id = None
            folio.save(
                update_fields=["canvas_id", "canvas_index", "canvas_label", "image_id"]
            )

        for key, folio in targets.items():
            row = rows_by_folio[key]
            if folio is None:
                folio = Folio(manuscript=manuscript, folio_number=row["folio"])
                created.append(folio)
                counts["created"] += 1
            elif (
                folio.canvas_id == row["id"]
                and folio.canvas_index == row["index"]
                and folio.canvas_label == row["label"]
                and folio.image_id == row["image_id"]
            ):
                continue
            if folio.canvas_id != row["id"]:
                counts["linked"] += 1
            folio.canvas_id = row["id"]
            folio.canvas_index = row["index"]
            folio.canvas_label = row["label"]
            folio.image_id = row["image_id"]
            folio.save()
    return counts, created
