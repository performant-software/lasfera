from django.core.management.base import BaseCommand
from django.db import transaction

from manuscript.models import Folio

# Folio records that were renamed to create a folio for the text, which carried
# their toponyms along with them, as found by comparing folio numbers with a
# December 2025 copy of the database (records still holding those toponyms on
# 2 Nov 2026). Cap1 and Fn3 were affected too, but researchers already fixed them.
# (siglum, record ID, current folio number, original folio number, toponym count)
REPAIRS = [
    ("Chig1", 34185, "3r", "13v", 3),
    ("Chig1", 33975, "3v-4r", "14v", 10),
    ("Chig2", 34181, "1r", "14v", 3),
    ("Chig2", 33973, "1v", "15v", 11),
    ("Chig2", 33746, "2r", "16r", 29),
    ("Borg", 34333, "16r", "25r", 14),
    ("Borg", 34049, "17v", "25v", 4),
]


class Command(BaseCommand):
    help = (
        "One-off repair: move toponyms from folio records that were renamed back "
        "to a record with their original folio number, creating it if needed. "
        "Nothing is renamed, and the renamed records keep their line ranges and "
        "images. Only reports what it would do unless run with --apply. A record "
        "is skipped if its folio number or toponym count isn't as expected, so "
        "running this again changes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Save the changes (default: report)"
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        moved = skipped = 0
        with transaction.atomic():
            for siglum, record_id, current, original, expected in REPAIRS:
                label = f"{siglum} #{record_id} {current} → {original}"
                problem = self.find_problem(
                    siglum, record_id, current, original, expected
                )
                if problem:
                    self.stdout.write(
                        self.style.WARNING(f"{label}: skipped ({problem})")
                    )
                    skipped += 1
                    continue

                folio = Folio.objects.get(pk=record_id)
                target = Folio.objects.filter(
                    manuscript=folio.manuscript, folio_number=original
                ).first()
                action = f"move to record #{target.pk}" if target else "create record"
                aliases = folio.locationalias_set.order_by("placename_alias")
                names = ", ".join(
                    alias.placename_alias or f"#{alias.pk}" for alias in aliases
                )
                self.stdout.write(f"{label}: {action}; {expected} toponyms: {names}")
                if apply:
                    if target is None:
                        target = Folio.objects.create(
                            manuscript=folio.manuscript, folio_number=original
                        )
                    folio.locationalias_set.update(folio=target)
                moved += expected

        prefix = "" if apply else "[not applied; use --apply to save] "
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Moved {moved} toponyms; skipped {skipped} records."
            )
        )

    def find_problem(self, siglum, record_id, current, original, expected):
        folio = Folio.objects.select_related("manuscript").filter(pk=record_id).first()
        if folio is None:
            return "record not found"
        if folio.manuscript is None or folio.manuscript.siglum != siglum:
            return f"it belongs to {folio.manuscript}"
        if folio.folio_number != current:
            return f'it is now numbered "{folio.folio_number}"'
        count = folio.locationalias_set.count()
        if count != expected:
            return f"it has {count} toponyms, not {expected}"
        matches = Folio.objects.filter(
            manuscript=folio.manuscript, folio_number=original
        ).count()
        if matches > 1:
            return f"{matches} records are numbered {original}"
        return None
