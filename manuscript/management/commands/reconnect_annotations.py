from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from manuscript.models import Stanza, StanzaTranslated

from textannotation.models import CrossReference, EditorialNote, TextualVariant


class Command(BaseCommand):
    help = "Match annotations to stanzas and translated stanzas based on text content and position"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--show-text",
            action="store_true",
            help="Show the surrounding text context for matches",
        )

    def find_all_positions(self, text, search_string):
        """Find all occurrences of search_string in text and return their positions"""
        positions = []
        start = 0
        while True:
            start = text.find(search_string, start)
            if start == -1:  # No more occurrences
                break
            positions.append((start, start + len(search_string)))
            start += 1  # Move past the current occurrence
        return positions

    def get_surrounding_context(self, text, start, end, context_chars=40):
        """Get text surrounding the match for context"""
        context_start = max(0, start - context_chars)
        context_end = min(len(text), end + context_chars)

        prefix = "..." if context_start > 0 else ""
        suffix = "..." if context_end < len(text) else ""

        return (
            f"{prefix}{text[context_start:start]}"
            f"[{text[start:end]}]"
            f"{text[end:context_end]}{suffix}"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        show_text = options["show_text"]

        # Get content types for both models
        stanza_type = ContentType.objects.get_for_model(Stanza)
        translated_type = ContentType.objects.get_for_model(StanzaTranslated)
        ct_map = {stanza_type.id: Stanza, translated_type.id: StanzaTranslated}
        processed = 0
        matched = 0
        not_found = 0
        ambiguous = 0

        # check all annotation types
        annotation_models = [EditorialNote, CrossReference, TextualVariant]

        for AnnotationModel in annotation_models:
            self.stdout.write(f"Processing {AnnotationModel.__name__}...")
            annotations = AnnotationModel.objects.all()
            processed += annotations.count()

            for annotation in annotations:
                selected_text = annotation.selected_text
                if not selected_text:
                    continue
                try:
                    # Try to convert position to integer, handle various formats
                    if isinstance(annotation.from_pos, dict):
                        # If it's stored as a JSON object, we might need different handling
                        self.stdout.write(
                            f"Position stored as JSON: {annotation.from_pos}"
                        )
                        continue
                    original_position = int(str(annotation.from_pos))
                except (ValueError, TypeError):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Could not parse position data for annotation {annotation.id}: {annotation.from_pos}"
                        )
                    )
                    original_position = None

                # try to find a match in the original object id, content type
                found_in_original = False
                if annotation.content_type_id in ct_map and annotation.object_id:
                    StanzaModel = ct_map[annotation.content_type_id]
                    try:
                        # fetch the specific object this annotation points to
                        target_obj = StanzaModel.objects.get(id=annotation.object_id)

                        # check if the text is still there
                        if (
                            target_obj.stanza_text
                            and selected_text in target_obj.stanza_text
                        ):
                            positions = self.find_all_positions(
                                target_obj.stanza_text, selected_text
                            )
                            best_match_pos = None

                            if len(positions) == 1:
                                best_match_pos = positions[0]
                            elif len(positions) > 1 and original_position is not None:
                                # disambiguate inside the same object
                                closest_distance = float("inf")
                                for start, end in positions:
                                    distance = abs(start - original_position)
                                    if distance < closest_distance:
                                        closest_distance = distance
                                        best_match_pos = (start, end)
                            if best_match_pos:
                                annotation.from_pos = best_match_pos[0]
                                annotation.to_pos = best_match_pos[1]
                                annotation.save()
                                found_in_original = True
                                self.stdout.write(
                                    f"Found match for {AnnotationModel.__name__} {annotation.id} "
                                    f"in {StanzaModel.__name__} {target_obj.id}"
                                )
                                if show_text:
                                    context = self.get_surrounding_context(
                                        target_obj.stanza_text,
                                        best_match_pos[0],
                                        best_match_pos[1],
                                    )
                                    self.stdout.write(f"Context: {context}")
                                matched += 1

                    except StanzaModel.DoesNotExist:
                        # original object is gone, proceed to fallback
                        pass

                if found_in_original:
                    # skip searching other model/instances if already found
                    continue

                matches_found = []

                # Search in both models
                for model, content_type in [
                    (Stanza, stanza_type),
                    (StanzaTranslated, translated_type),
                ]:
                    for obj in model.objects.filter(
                        stanza_text__contains=selected_text
                    ):
                        # Find all occurrences in this object
                        positions = self.find_all_positions(
                            obj.stanza_text, selected_text
                        )

                        for start, end in positions:
                            matches_found.append(
                                {
                                    "model": model.__name__,
                                    "object": obj,
                                    "start": start,
                                    "end": end,
                                    "content_type": content_type,
                                }
                            )

                if len(matches_found) == 1:
                    # Single match - straightforward case
                    match = matches_found[0]
                    if not dry_run:
                        annotation.content_type = match["content_type"]
                        annotation.object_id = match["object"].id
                        annotation.from_pos = match["start"]
                        annotation.to_pos = match["end"]
                        annotation.save()

                    self.stdout.write(
                        f"Found single match for {AnnotationModel.__name__} {annotation.id} "
                        f"in {match['model']} {match['object'].id}"
                    )
                    if show_text:
                        context = self.get_surrounding_context(
                            match["object"].stanza_text, match["start"], match["end"]
                        )
                        self.stdout.write(f"Context: {context}")

                    matched += 1

                elif len(matches_found) > 1:
                    # Multiple matches - try to use position data to disambiguate
                    best_match = None
                    if original_position is not None:
                        # Find the match closest to the original position
                        closest_distance = float("inf")
                        for match in matches_found:
                            distance = abs(match["start"] - original_position)
                            if distance < closest_distance:
                                closest_distance = distance
                                best_match = match

                    if (
                        best_match and closest_distance < 50
                    ):  # Threshold for position matching
                        if not dry_run:
                            annotation.content_type = best_match["content_type"]
                            annotation.object_id = best_match["object"].id
                            annotation.from_pos = best_match["start"]
                            annotation.to_pos = best_match["end"]
                            annotation.save()

                        self.stdout.write(
                            f"Found best position match for {AnnotationModel.__name__} {annotation.id} "
                            f"in {best_match['model']} {best_match['object'].id}"
                        )
                        matched += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Multiple matches ({len(matches_found)}) found for {AnnotationModel.__name__} {annotation.id}: "
                                f"'{selected_text[:50]}...'"
                            )
                        )
                        if show_text:
                            for i, match in enumerate(matches_found, 1):
                                context = self.get_surrounding_context(
                                    match["object"].stanza_text,
                                    match["start"],
                                    match["end"],
                                )
                                self.stdout.write(
                                    f"  {i}. In {match['model']} {match['object'].id}: {context}"
                                )
                        ambiguous += 1

                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"No match found for {AnnotationModel.__name__} {annotation.id}: "
                            f"'{selected_text[:50]}...'"
                        )
                    )
                    not_found += 1

        # Print summary
        self.stdout.write("\nSummary:")
        self.stdout.write(f"Total annotations processed: {processed}")
        self.stdout.write(f"Successfully matched: {matched}")
        self.stdout.write(f"Ambiguous (multiple matches): {ambiguous}")
        self.stdout.write(f"No matches found: {not_found}")

        if dry_run:
            self.stdout.write("\nThis was a dry run - no changes were made")
