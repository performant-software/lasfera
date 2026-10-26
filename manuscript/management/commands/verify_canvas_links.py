from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from manuscript.models import SingleManuscript
from manuscript.utils import fetch_manifest, get_canvases, normalize_folio_label

CANVAS_FIELDS = ["canvas_id", "canvas_index", "canvas_label", "image_id"]


class Command(BaseCommand):
    help = (
        "Check that each folio's linked IIIF canvas is still in its manuscript's "
        "manifest. Canvases that moved or were relabelled are updated; folios "
        "whose canvas is gone are re-linked by image ID, or by position and "
        "label; anything that can't be re-linked is reported and left as it is. "
        "Meant to be run regularly, e.g. from a scheduler."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "sigla",
            nargs="*",
            help="Sigla of manuscripts to check (default: all with linked folios)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving",
        )

    def handle(self, *args, **options):
        manuscripts = (
            SingleManuscript.objects.exclude(iiif_url__isnull=True)
            .exclude(iiif_url="")
            .filter(folio__canvas_id__isnull=False)
            .distinct()
            .order_by("siglum")
        )
        if options["sigla"]:
            manuscripts = manuscripts.filter(siglum__in=options["sigla"])

        totals = Counter()
        for manuscript in manuscripts:
            totals.update(self.verify_manuscript(manuscript, options["dry_run"]))

        prefix = "[dry run] " if options["dry_run"] else ""
        summary = (
            f"\n{prefix}Checked {totals['checked']} linked folios: "
            f"{totals['ok']} unchanged, {totals['updated']} updated, "
            f"{totals['relinked']} re-linked, {totals['broken']} could not be "
            f"re-linked; {totals['unchecked']} manifests could not be loaded."
        )
        style = (
            self.style.WARNING
            if totals["broken"] or totals["unchecked"]
            else self.style.SUCCESS
        )
        self.stdout.write(style(summary))

    def verify_manuscript(self, manuscript, dry_run):
        counts = Counter()
        label = manuscript.siglum or f"Manuscript {manuscript.pk}"
        try:
            canvases = get_canvases(fetch_manifest(manuscript.iiif_url))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"{label}: could not load manifest ({e})")
            )
            counts["unchecked"] += 1
            return counts

        canvases_by_id = {canvas["id"]: canvas for canvas in canvases}
        canvases_by_image = defaultdict(list)
        for canvas in canvases:
            if canvas["image_id"]:
                canvases_by_image[canvas["image_id"]].append(canvas)

        folios = list(manuscript.folio_set.exclude(canvas_id__isnull=True))
        # canvases held by a valid link, which a re-linked folio can't take
        used_canvas_ids = {
            folio.canvas_id for folio in folios if folio.canvas_id in canvases_by_id
        }

        notes = defaultdict(list)
        with transaction.atomic():
            for folio in folios:
                counts["checked"] += 1
                canvas = canvases_by_id.get(folio.canvas_id)
                if canvas:
                    if self.canvas_changed(folio, canvas):
                        notes["position or label changed"].append(
                            self.describe(folio, canvas)
                        )
                        self.apply_canvas(folio, canvas, dry_run)
                        counts["updated"] += 1
                    else:
                        counts["ok"] += 1
                    continue

                canvas, method = self.find_moved_canvas(
                    folio, canvases, canvases_by_image
                )
                if canvas and canvas["id"] not in used_canvas_ids:
                    notes[f"re-linked by {method}"].append(self.describe(folio, canvas))
                    self.apply_canvas(folio, canvas, dry_run)
                    used_canvas_ids.add(canvas["id"])
                    counts["relinked"] += 1
                elif canvas:
                    notes[
                        "canvas gone, and its replacement is linked to another folio"
                    ].append(folio.folio_number or f"#{folio.pk}")
                    counts["broken"] += 1
                else:
                    notes["canvas gone, and no replacement found"].append(
                        folio.folio_number or f"#{folio.pk}"
                    )
                    counts["broken"] += 1

        summary = (
            f"{label}: {counts['checked']} linked folios, {counts['ok']} unchanged, "
            f"{counts['updated']} updated, {counts['relinked']} re-linked, "
            f"{counts['broken']} could not be re-linked"
        )
        if counts["broken"]:
            self.stdout.write(self.style.WARNING(summary))
        elif notes:
            self.stdout.write(summary)
        for note, items in notes.items():
            self.stdout.write(f"    {note}: {', '.join(items)}")
        return counts

    def find_moved_canvas(self, folio, canvases, canvases_by_image):
        """Find the canvas a folio's missing canvas has become: the one showing
        the same image, or else the one at the same position with the same
        label. Returns (canvas, method) or (None, None)."""
        matches = canvases_by_image.get(folio.image_id or "", [])
        if len(matches) == 1:
            return matches[0], "image ID"
        index = folio.canvas_index
        if (
            index is not None
            and index < len(canvases)
            and folio.canvas_label
            and normalize_folio_label(canvases[index]["label"])
            == normalize_folio_label(folio.canvas_label)
        ):
            return canvases[index], "position and label"
        return None, None

    def canvas_changed(self, folio, canvas):
        return (
            folio.canvas_index != canvas["index"]
            or (folio.canvas_label or "") != canvas["label"][:255]
            or (canvas["image_id"] and folio.image_id != canvas["image_id"])
        )

    def describe(self, folio, canvas):
        return f"{folio.folio_number or f'#{folio.pk}'} (now image {canvas['index'] + 1}, \"{canvas['label']}\")"

    def apply_canvas(self, folio, canvas, dry_run):
        folio.canvas_id = canvas["id"]
        folio.canvas_index = canvas["index"]
        folio.canvas_label = canvas["label"][:255]
        folio.image_id = canvas["image_id"] or folio.image_id
        if not dry_run:
            folio.save(update_fields=CANVAS_FIELDS)
