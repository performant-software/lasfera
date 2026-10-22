import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from manuscript.models import SingleManuscript
from manuscript.utils import fetch_manifest, get_canvases, normalize_folio_label

# folio numbers copied from the viewer's page menu: "<canvas position> : <label>"
VIEWER_PAGE_REFERENCE = re.compile(r"^\s*(\d+)\s*:\s*(.+?)\s*$")
# a normalized recto/verso folio number, e.g. "12r" or "iv" (i verso)
RECTO_VERSO = re.compile(r"(\d+|[ivxlc]+)[rv]")


class Command(BaseCommand):
    help = (
        "Link folios to canvases in each manuscript's IIIF manifest. A folio is "
        "linked only when its recto/verso folio number matches exactly one "
        "canvas label, or when it was copied from the viewer's page menu "
        '("5 : 1r") and canvas 5 has that label, in which case it is also '
        "renamed to the label. Everything else is reported so it can be linked "
        "by hand."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "sigla",
            nargs="*",
            help="Sigla of manuscripts to process (default: all with a IIIF manifest)",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Re-match folios that already have a canvas ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be linked without saving",
        )

    def handle(self, *args, **options):
        manuscripts = (
            SingleManuscript.objects.exclude(iiif_url__isnull=True)
            .exclude(iiif_url="")
            .order_by("siglum")
        )
        if options["sigla"]:
            manuscripts = manuscripts.filter(siglum__in=options["sigla"])
            missing = set(options["sigla"]) - set(
                manuscripts.values_list("siglum", flat=True)
            )
            for siglum in sorted(missing):
                self.stdout.write(
                    self.style.WARNING(f"{siglum}: not found or has no IIIF manifest")
                )

        totals = Counter()
        for manuscript in manuscripts:
            if not manuscript.folio_set.exists():
                continue
            counts = self.link_manuscript(
                manuscript, options["overwrite"], options["dry_run"]
            )
            totals.update(counts)

        prefix = "[dry run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Linked {totals['linked']} folios "
                f"(renamed {totals['renamed']}); "
                f"{totals['already_linked']} were already linked; "
                f"{totals['unresolved']} still need to be linked by hand; "
                f"{totals['needs_folio_number']} linked folios need a correct "
                "folio number."
            )
        )

    def link_manuscript(self, manuscript, overwrite, dry_run):
        counts = Counter()
        label = manuscript.siglum or f"Manuscript {manuscript.pk}"
        try:
            canvases = get_canvases(fetch_manifest(manuscript.iiif_url))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"{label}: could not load manifest ({e})")
            )
            return counts

        canvases_by_id = {canvas["id"]: canvas for canvas in canvases}
        canvases_by_label = defaultdict(list)
        for canvas in canvases:
            canvases_by_label[normalize_folio_label(canvas["label"])].append(canvas)

        folios = list(manuscript.folio_set.all())
        folio_label_counts = Counter(
            normalize_folio_label(folio.folio_number) for folio in folios
        )
        used_canvas_ids = {
            folio.canvas_id for folio in folios if folio.canvas_id and not overwrite
        }

        problems = defaultdict(list)
        notes = defaultdict(list)
        with transaction.atomic():
            for folio in folios:
                if folio.canvas_id and not overwrite:
                    counts["already_linked"] += 1
                    # fill in canvas details for IDs that were entered by hand
                    canvas = canvases_by_id.get(folio.canvas_id)
                    if canvas and folio.canvas_index is None:
                        self.apply_canvas(folio, canvas, dry_run)
                    continue

                page_reference = VIEWER_PAGE_REFERENCE.match(folio.folio_number or "")
                if page_reference:
                    position, page_label = page_reference.groups()
                    position = int(position)
                    canvas = (
                        canvases[position - 1]
                        if 0 < position <= len(canvases)
                        else None
                    )
                    if not canvas or normalize_folio_label(
                        canvas["label"]
                    ) != normalize_folio_label(page_label):
                        problems[
                            "viewer page reference does not match the manifest"
                        ].append(folio.folio_number)
                    elif canvas["id"] in used_canvas_ids:
                        problems["canvas already linked to another folio"].append(
                            folio.folio_number
                        )
                    else:
                        update_fields = []
                        new_label = normalize_folio_label(page_label)
                        if (
                            RECTO_VERSO.fullmatch(new_label)
                            and not folio_label_counts[new_label]
                        ):
                            notes["renamed"].append(
                                f"{folio.folio_number} → {page_label}"
                            )
                            folio.folio_number = page_label
                            folio_label_counts[new_label] += 1
                            update_fields.append("folio_number")
                            counts["renamed"] += 1
                        else:
                            notes[
                                "linked, but the folio number needs correcting"
                            ].append(folio.folio_number)
                            counts["needs_folio_number"] += 1
                        self.apply_canvas(folio, canvas, dry_run, update_fields)
                        used_canvas_ids.add(canvas["id"])
                        counts["linked"] += 1
                    continue

                folio_label = normalize_folio_label(folio.folio_number)
                matches = canvases_by_label.get(folio_label, [])
                if not folio_label:
                    problems["no folio number"].append(f"#{folio.pk}")
                elif not folio_label.endswith(("r", "v")):
                    # bare numbers are too easily confused with the image
                    # sequence numbers some manifests use as labels
                    problems["not a recto/verso folio number"].append(
                        folio.folio_number
                    )
                elif folio_label_counts[folio_label] > 1:
                    problems["folio number used more than once"].append(
                        folio.folio_number
                    )
                elif not matches:
                    problems["no canvas with this label"].append(folio.folio_number)
                elif len(matches) > 1:
                    problems["several canvases with this label"].append(
                        folio.folio_number
                    )
                elif matches[0]["id"] in used_canvas_ids:
                    problems["canvas already linked to another folio"].append(
                        folio.folio_number
                    )
                else:
                    self.apply_canvas(folio, matches[0], dry_run)
                    used_canvas_ids.add(matches[0]["id"])
                    counts["linked"] += 1

        counts["unresolved"] = sum(len(items) for items in problems.values())
        summary = (
            f"{label}: linked {counts['linked']}, "
            f"already linked {counts['already_linked']}, "
            f"unresolved {counts['unresolved']} "
            f"(of {len(folios)} folios, {len(canvases)} canvases)"
        )
        style = self.style.WARNING if problems else self.style.SUCCESS
        self.stdout.write(style(summary))
        for problem, items in [*problems.items(), *notes.items()]:
            self.stdout.write(f"    {problem}: {', '.join(sorted(set(items)))}")
        return counts

    def apply_canvas(self, folio, canvas, dry_run, update_fields=()):
        folio.canvas_id = canvas["id"]
        folio.canvas_index = canvas["index"]
        folio.canvas_label = canvas["label"][:255]
        folio.image_id = canvas["image_id"]
        if not dry_run:
            folio.save(
                update_fields=[
                    "canvas_id",
                    "canvas_index",
                    "canvas_label",
                    "image_id",
                    *update_fields,
                ]
            )
