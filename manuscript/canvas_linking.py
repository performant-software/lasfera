"""Linking a manuscript's folios to the canvases of its IIIF manifest by hand"""

from collections import Counter, defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction

from manuscript.models import Folio
from manuscript.utils import normalize_folio_label

FOLIO_NUMBER_MAX_LENGTH = Folio._meta.get_field("folio_number").max_length
CANVAS_ID_MAX_LENGTH = Folio._meta.get_field("canvas_id").max_length


def folio_key(number):
    """Key for matching folio numbers, ignoring differences like "f. 12r" and
    "12r\" """
    return normalize_folio_label(number) or (number or "").lower()


def clean_canvas_rows(rows):
    """Validate the rows submitted from the canvas linking page. Each row is a
    canvas from the manifest: id, index, label, image_id, and the folio
    numbers entered for it, as an image can show more than one folio."""
    if not isinstance(rows, list):
        raise ValidationError("The submitted images could not be read.")

    cleaned = []
    for row in rows:
        try:
            canvas_id = str(row["id"]).strip()
            index = int(row["index"])
            label = str(row.get("label") or "").strip()[:255]
            image_id = str(row.get("image_id") or "").strip() or None
            if not isinstance(row.get("folios", []), list):
                raise TypeError
            numbers = [str(number).strip() for number in row.get("folios", [])]
        except (KeyError, TypeError, ValueError):
            raise ValidationError("The submitted images could not be read.")
        if not canvas_id or len(canvas_id) > CANVAS_ID_MAX_LENGTH or index < 0:
            raise ValidationError("The submitted images could not be read.")
        if image_id and len(image_id) > CANVAS_ID_MAX_LENGTH:
            image_id = None
        if any(len(number) > FOLIO_NUMBER_MAX_LENGTH for number in numbers):
            raise ValidationError(
                f"The folio number entered for image {index + 1} is too long."
            )
        # one entry per folio, ignoring blanks and repeats within the row
        folios_by_key = {}
        for number in numbers:
            if number:
                folios_by_key.setdefault(folio_key(number), number)
        cleaned.append(
            {
                "id": canvas_id,
                "index": index,
                "label": label,
                "image_id": image_id,
                "folios": list(folios_by_key.values()),
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
    differences like "f. 12r" and "12r"), or a new folio is created. A canvas
    can have several folios, but a folio has one canvas. Folios are never
    renamed or deleted: a folio removed from a canvas is only unlinked, so its
    toponyms and other data stay intact.

    Returns a Counter of linked, unlinked, and created folios, and a list of
    the folios created. Raises ValidationError, without saving anything, if
    the entries conflict."""
    errors = []

    # folio number key -> (row, number as entered), checking no folio is
    # entered for two canvases
    entries_by_folio = defaultdict(list)
    for row in rows:
        for number in row["folios"]:
            entries_by_folio[folio_key(number)].append((row, number))
    for entered in entries_by_folio.values():
        if len(entered) > 1:
            positions = ", ".join(str(row["index"] + 1) for row, _ in entered)
            errors.append(
                f'Folio "{entered[0][1]}" is entered for more than one image '
                f"({positions}). Each folio can be linked to one image."
            )
    rows_by_folio = {key: entered[-1] for key, entered in entries_by_folio.items()}

    folios = list(manuscript.folio_set.all())
    folios_by_key = defaultdict(list)
    for folio in folios:
        key = folio_key(folio.folio_number)
        if key:
            folios_by_key[key].append(folio)

    targets = {}  # folio number key -> existing folio, or None to create
    for key, (row, number) in rows_by_folio.items():
        matches = folios_by_key.get(key, [])
        if len(matches) > 1:
            numbers = ", ".join(sorted(f'"{f.folio_number}"' for f in matches))
            errors.append(
                f'Folio "{number}" matches several folio records in this '
                f"manuscript ({numbers}). Merge or renumber those folio records "
                "first."
            )
        elif matches:
            targets[key] = matches[0]
        elif not can_create:
            errors.append(
                f'There is no folio record "{number}" in this manuscript, '
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
        folio.pk: rows_by_folio[key][0]["id"]
        for key, folio in targets.items()
        if folio is not None
    }
    with transaction.atomic():
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
            row, number = rows_by_folio[key]
            if folio is None:
                folio = Folio(manuscript=manuscript, folio_number=number)
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
