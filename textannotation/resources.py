from django.contrib.contenttypes.models import ContentType
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget

from manuscript.models import SingleManuscript, Stanza, StanzaTranslated
from textannotation.models import TextualVariant


class TextualVariantResource(resources.ModelResource):
    """Resource for importing TextualVariant records"""

    selected_text = fields.Field(attribute="selected_text", column_name="TextSegment")
    annotation = fields.Field(attribute="annotation", column_name="Variant")
    manuscript_siglum = fields.Field(
        column_name="Siglum",
        attribute="manuscript__siglum",
        readonly=True,
    )
    content_type = fields.Field(
        attribute="content_type", widget=ForeignKeyWidget(ContentType, "id")
    )
    object_id = fields.Field(attribute="object_id")
    variant_id = fields.Field(attribute="variant_id", column_name="VariantID")
    manuscript = fields.Field(
        attribute="manuscript",
        widget=ForeignKeyWidget(SingleManuscript, "id"),
        column_name="manuscript",
    )
    significance = fields.Field("significance", column_name="Significance")
    family_id = fields.Field("family_id", column_name="FamilyID")
    editor_initials = fields.Field("editor_initials", column_name="Editor")
    notes = fields.Field("notes", column_name="Notes")

    class Meta:
        model = TextualVariant
        import_id_fields = ("variant_id",)
        fields = (
            "variant_id",
            "manuscript_siglum",
            "selected_text",
            "annotation_text",
            "significance",
            "family_id",
            "editor_initials",
            "notes",
            "annotation",
            "manuscript",
            "content_type",
            "object_id",
        )

    def before_import_row(self, row, **kwargs):
        # process line codes
        row_line_code_start = row.get("LineCodeStart")
        if not row_line_code_start:
            row["_skip"] = True
            return

        row_line_code_end = row.get("LineCodeEnd")
        multi_line = row_line_code_end != row_line_code_start
        line_code_start = ".".join(
            f"{int(part):02d}" for part in row_line_code_start.split(".")
        )
        line_code_end = ".".join(
            f"{int(part):02d}" for part in row_line_code_end.split(".")
        )
        if multi_line and line_code_end < line_code_start:
            raise ValueError(
                f"LineCodeStart {row_line_code_start} is after LineCodeEnd {row_line_code_end}. Cannot parse."
            )

        # NOTE: assumes Stanza (not Translated) because these are Textual Variants
        stanza = Stanza.objects.filter(
            stanza_line_code_starts=line_code_start,
        ).first()
        if not stanza:
            # no stanza found for line code; skip
            row["_skip"] = True
            return

        # set GFK properties
        row["content_type"] = ContentType.objects.get_for_model(Stanza).id
        row["object_id"] = stanza.id

        # get manuscript by siglum
        siglum = row.get("Siglum")
        manuscript = SingleManuscript.objects.filter(siglum=siglum).first()
        if not manuscript:
            # error: prompt to create manuscript first
            raise ValueError(
                f"Manuscript with siglum '{siglum}' does not exist. "
                f"Please create the manuscript record before importing variants."
            )
        row["manuscript"] = manuscript.id

        # handle text selection
        stanza_text = stanza.stanza_text or ""
        is_rubric = line_code_start.endswith(".00")
        if is_rubric:
            # for rubrics, select the whole thing
            row["from_pos"] = 0
            row["to_pos"] = len(stanza_text)
            row["TextSegment"] = stanza_text
        elif multi_line:
            # for multi-line variant annotations, select the first word
            first_word = stanza_text.split()[0] if stanza_text else ""
            row["from_pos"] = 0
            row["to_pos"] = len(first_word) if stanza_text else {}
            row["TextSegment"] = first_word
        else:
            # atempt to locate the selected text in the stanza text
            snippet = row.get("TextSegment", "")
            idx = stanza_text.find(snippet)
            row["from_pos"], row["to_pos"] = (
                (idx, idx + len(snippet)) if idx != -1 else ({}, {})
            )

        variant = (row.get("Variant") or "").strip()
        existing_notes = row.get("Notes") or ""
        if multi_line and variant:
            # for multi-line annotations, put the "Variant" content in the
            # notes field, and leave the Variant field empty
            row["Variant"] = None
            row["Notes"] = (
                f"{variant} ({existing_notes})" if existing_notes else variant
            )
        else:
            row["Variant"] = variant

        row["editor_initials"] = row.get("Editor")

    def skip_row(self, instance, original, row, import_validation_errors=None):
        """skip a row if the line code did not match any stanza"""
        if row.get("_skip"):
            return True
        return super().skip_row(
            instance, original, row, import_validation_errors=import_validation_errors
        )

    def get_instance(self, instance_loader, row):
        """update any existing records by VariantID"""
        return self.get_queryset().filter(variant_id=row.get("VariantID")).first()
