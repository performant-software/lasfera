import json

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.contrib.contenttypes.admin import GenericTabularInline
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Value
from django.db.models.functions import Concat
from django.forms.models import BaseInlineFormSet
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from import_export.admin import ImportExportModelAdmin

from common.admin import StripDivMixin
from manuscript.canvas_linking import clean_canvas_rows, link_canvases
from manuscript.models import (
    AuthorityFile,
    Codex,
    Detail,
    EditorialStatus,
    Folio,
    Library,
    LineCode,
    Location,
    LocationAlias,
    ManuscriptFamily,
    Reference,
    SingleManuscript,
    Stanza,
    StanzaTranslated,
    TextDecoration,
    ViewerNote,
)
from manuscript.resources import (
    ReferenceResource,
    SingleManuscriptResource,
    FolioResource,
    LocationResource,
    LocationAliasResource,
    LineCodeResource,
)
from manuscript.utils import normalize_folio_label
from textannotation.admin import (
    CrossReferenceAdminForm,
    EditorialNoteAdminForm,
    TextualVariantAdminForm,
)
from textannotation.models import CrossReference, EditorialNote, TextualVariant


# Admin site configuration --------------------------------
admin.site.site_header = "La Sfera Admin"
admin.site.site_title = "La Sfera Admin Portal"
admin.site.index_title = "Welcome to the La Sfera Manuscript Portal"


# Inline models -------------------------------------------
class StanzaInline(admin.StackedInline):
    model = Stanza
    extra = 1
    fields = (
        "stanza_line_code_starts",
        "stanza_line_code_ends",
        "stanza_text",
        "stanza_notes",
    )


def folio_toponym_count(folio):
    """How many toponym aliases are attached to a folio record"""
    if not folio.pk:
        return 0
    count = getattr(folio, "toponym_total", None)
    return folio.locationalias_set.count() if count is None else count


def folio_number_taken(folio, manuscript, number):
    """Whether another folio of the manuscript has this number, ignoring
    differences like "f. 12r" and "12r\""""
    key = normalize_folio_label(number)
    if not manuscript or not key:
        return False
    others = Folio.objects.filter(manuscript=manuscript).exclude(pk=folio.pk)
    return any(
        normalize_folio_label(other) == key
        for other in others.values_list("folio_number", flat=True)
    )


def folio_toponym_rows(folio):
    """A folio's toponym aliases, as (alias admin URL, alias, toponym link)"""
    aliases = folio.locationalias_set.select_related("location").order_by(
        "placename_alias", "id"
    )
    rows = []
    for alias in aliases:
        if alias.location:
            location = alias.location
            name = location.name or location.placename_modern or ""
            toponym = format_html(
                '<a href="{}">{}</a> {}',
                reverse("admin:manuscript_location_change", args=[location.pk]),
                name or location.placename_id,
                f"({location.placename_id})" if name else "",
            )
        else:
            toponym = "-"
        rows.append(
            (
                reverse("admin:manuscript_locationalias_change", args=[alias.pk]),
                alias.placename_alias or f"Alias {alias.pk}",
                toponym,
            )
        )
    return rows


class FolioAdminForm(forms.ModelForm):
    class Meta:
        model = Folio
        fields = "__all__"
        help_texts = {
            "folio_number": "The folio's number in the manuscript, e.g. 12r, as "
            "shown to readers.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            if "folio_number" in self.fields:
                self.fields["folio_number"].required = True
            if "manuscript" in self.fields:
                self.fields["manuscript"].required = True

    def clean(self):
        cleaned_data = super().clean()
        if "folio_number" in self.changed_data:
            number = cleaned_data.get("folio_number")
            manuscript = cleaned_data.get("manuscript", self.instance.manuscript)
            if folio_number_taken(self.instance, manuscript, number):
                self.add_error(
                    "folio_number",
                    f'{manuscript} already has a folio numbered "{number}".',
                )
        if "canvas_id" in self.changed_data:
            # the recorded canvas details describe the previously linked
            # canvas, so drop them when the canvas ID is changed by hand
            self.instance.canvas_index = None
            self.instance.canvas_label = None
            self.instance.image_id = None
        return cleaned_data


def linked_image_link(folio, thumbnail=False):
    """Link to a folio's row on the canvas linking page, labelled with the
    linked image's position and manifest label"""
    url = reverse(
        "admin:manuscript_singlemanuscript_canvases", args=[folio.manuscript_id]
    )
    if not folio.canvas_id:
        return format_html('<a href="{}">Not linked</a>', url)
    position = (
        f"Image {folio.canvas_index + 1}" if folio.canvas_index is not None else "Image"
    )
    label = f" · {folio.canvas_label}" if folio.canvas_label else ""
    image = ""
    if thumbnail and folio.image_id:
        # image_id is usually a IIIF image service; drop the preview if not
        image = format_html(
            '<img src="{}/full/!200,200/0/default.jpg" alt="" loading="lazy" '
            'style="display: block; max-width: 200px; max-height: 200px; '
            'margin-bottom: 4px;" onerror="this.remove()">',
            folio.image_id,
        )
    # the canvas linking page scrolls to and highlights this folio's row
    return format_html(
        '<a href="{}#folio-{}">{}{}{}</a>', url, folio.pk, image, position, label
    )


class FolioInlineForm(forms.ModelForm):
    class Meta:
        model = Folio
        fields = ("folio_number", "line_code_range_start", "line_code_range_end")
        help_texts = {
            "folio_number": "Numbers of folios with toponyms are changed on the "
            "folio's own page.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if folio_toponym_count(self.instance):
            self.fields["folio_number"].disabled = True
        if not self.instance.pk:
            self.fields["folio_number"].required = True

    def clean(self):
        cleaned_data = super().clean()
        number = cleaned_data.get("folio_number")
        if "folio_number" in self.changed_data and folio_number_taken(
            self.instance, self.instance.manuscript, number
        ):
            self.add_error(
                "folio_number",
                f'{self.instance.manuscript} already has a folio numbered "{number}".',
            )
        return cleaned_data


class FolioInlineFormSet(BaseInlineFormSet):
    def clean(self):
        """Folio numbers added or changed together can't repeat each other"""
        super().clean()
        seen = set()
        for form in self.forms:
            if "folio_number" not in form.changed_data:
                continue
            number = form.cleaned_data.get("folio_number")
            key = normalize_folio_label(number)
            if key and key in seen:
                form.add_error(
                    "folio_number", f'Folio "{number}" is entered more than once.'
                )
            seen.add(key)


class FolioInline(admin.TabularInline):
    """Compact list of a manuscript's folios for adding folios and editing line
    ranges. Other details are edited on each folio's own page, and images are
    linked on the Link IIIF canvases page. Folios aren't deleted here: deleting
    a folio also deletes its toponym aliases."""

    model = Folio
    form = FolioInlineForm
    formset = FolioInlineFormSet
    classes = ("collapse",)
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "folio_number",
        "line_code_range_start",
        "line_code_range_end",
        "toponym_count",
        "linked_image",
    )
    readonly_fields = ("toponym_count", "linked_image")
    ordering = ("canvas_index", "folio_number")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(toponym_total=Count("locationalias"))
        )

    @admin.display(description="Toponyms")
    def toponym_count(self, folio):
        return folio_toponym_count(folio) if folio.pk else "-"

    @admin.display(description="Linked image")
    def linked_image(self, folio):
        return linked_image_link(folio) if folio.pk else "-"


class DetailInline(admin.StackedInline):
    model = Detail
    classes = ("collapse",)
    extra = 1
    max_num = 1


class TextDecorationInline(admin.StackedInline):
    model = TextDecoration
    classes = ("collapse",)
    extra = 1
    max_num = 1


class ReferenceInline(admin.StackedInline):
    model = Reference
    classes = ("collapse",)
    extra = 1


class EditorialStatusInline(admin.StackedInline):
    model = EditorialStatus
    classes = ("collapse",)
    extra = 1
    max_num = 1


class ViewerNotesInline(admin.StackedInline):
    model = ViewerNote
    classes = ("collapse",)
    extra = 1


class CodexInline(admin.StackedInline):
    model = Codex
    classes = ("collapse",)
    extra = 1
    max_num = 1


class LocationAliasInline(admin.TabularInline):
    model = LocationAlias
    extra = 1
    autocomplete_fields = ("manuscript", "folio")


class AuthorityFileInline(admin.TabularInline):
    model = AuthorityFile
    extra = 1


class BaseAnnotationInline(GenericTabularInline):
    """Inline mixin"""

    readonly_fields = ("selected_text", "link_status")

    @admin.display(description="Link Status")
    def link_status(self, obj):
        if not obj.id or not obj.content_object:
            return "—"

        parent_text = obj.content_object.stanza_text
        # get offset
        offset = (
            obj.from_pos.get("offset", 0)
            if isinstance(obj.from_pos, dict)
            else (obj.from_pos or 0)
        )

        # selected_text is present and in the right place
        if parent_text[offset : offset + len(obj.selected_text)] == obj.selected_text:
            return "✔"

        # text has shifted, annotation may be broken
        elif obj.selected_text in parent_text:
            return format_html('<span style="color: orange;">⚠ Possibly broken</span>')

        # broken: cannot associate text
        return format_html(
            '<span style="color: red; font-weight: bold;">✖ Broken</span>'
        )


class EditorialNoteInline(BaseAnnotationInline):
    model = EditorialNote
    extra = 0
    fields = ("link_status", "selected_text", "annotation")
    form = EditorialNoteAdminForm


class CrossReferenceInline(BaseAnnotationInline):
    model = CrossReference
    extra = 0
    fields = ("link_status", "selected_text", "annotation")
    form = CrossReferenceAdminForm


class TextualVariantInline(BaseAnnotationInline):
    model = TextualVariant
    extra = 0
    fields = (
        "link_status",
        "selected_text",
        "annotation",
        "manuscript",
        "significance",
        "notes",
        "variant_id",
        "editor_initials",
    )
    form = TextualVariantAdminForm


class ManuscriptTextualVariantsInline(admin.TabularInline):
    """Inline to display all textual variants read-only on manuscript"""

    model = TextualVariant
    extra = 0
    classes = ("collapse",)

    fields = (
        "line_code_display",
        "selected_text",
        "variant_text_display",
        "significance",
        "notes",
        "variant_id",
        "editor_initials",
    )

    # all fields read-only
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields] + [
            "line_code_display",
            "variant_text_display",
        ]

    # prevents adding or deleting from within the Manuscript page
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Line code")
    def line_code_display(self, obj):
        """show line code and lnk to the Stanza or StanzaTranslated"""
        target = obj.content_object
        if target and hasattr(target, "stanza_line_code_starts"):
            app_label = target._meta.app_label
            model_name = target._meta.model_name
            url = reverse(f"admin:{app_label}_{model_name}_change", args=[target.id])
            return format_html(
                '<a href="{}">{}</a>', url, target.stanza_line_code_starts
            )
        return "N/A"

    @admin.display(description="Variant text")
    def variant_text_display(self, obj):
        admin_url = reverse("admin:textannotation_textualvariant_change", args=[obj.id])
        return format_html(f'<a href="{admin_url}">{obj.annotation}</a>')


class ManuscriptFamilyInline(admin.TabularInline):
    model = ManuscriptFamily.manuscripts.through
    classes = ("collapse",)
    autocomplete_fields = ["manuscriptfamily"]
    extra = 1
    verbose_name = "Family"
    verbose_name_plural = "Families"


# Custom admin models -------------------------------------
@admin.register(SingleManuscript)
class SingleManuscriptAdmin(ImportExportModelAdmin):
    inlines = [
        AuthorityFileInline,
        TextDecorationInline,
        ReferenceInline,
        DetailInline,
        CodexInline,
        ViewerNotesInline,
        EditorialStatusInline,
        FolioInline,
        ManuscriptFamilyInline,
        ManuscriptTextualVariantsInline,
    ]
    list_display = (
        "siglum",
        "shelfmark",
        "library",
        "manuscript_lost",
        "manuscript_destroyed",
        "has_iiif_url",
        "item_id",
    )
    search_fields = ("siglum",)
    resource_class = SingleManuscriptResource
    list_filter = [
        ("family", admin.RelatedOnlyFieldListFilter),
        "library",
    ]

    change_form_template = "admin/manuscript/singlemanuscript/change_form.html"

    @admin.display(boolean=True, description="IIIF Available")
    def has_iiif_url(self, obj):
        return bool(obj.iiif_url)

    def get_urls(self):
        return [
            path(
                "<path:object_id>/canvases/",
                self.admin_site.admin_view(self.link_canvases_view),
                name="manuscript_singlemanuscript_canvases",
            ),
            *super().get_urls(),
        ]

    def link_canvases_view(self, request, object_id):
        """Page for linking the manuscript's folios to its IIIF canvases by hand"""
        manuscript = self.get_object(request, unquote(object_id))
        if manuscript is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)
        if not request.user.has_perm("manuscript.change_folio"):
            raise PermissionDenied

        change_url = reverse(
            "admin:manuscript_singlemanuscript_change", args=[manuscript.pk]
        )
        if not manuscript.iiif_url:
            messages.warning(request, "This manuscript has no IIIF manifest URL.")
            return redirect(change_url)

        can_create = request.user.has_perm("manuscript.add_folio")
        submitted = None
        if request.method == "POST":
            try:
                raw_rows = json.loads(request.POST.get("rows", ""))
            except ValueError:
                raw_rows = None
            try:
                rows = clean_canvas_rows(raw_rows)
                counts, created = link_canvases(manuscript, rows, can_create=can_create)
            except ValidationError as e:
                for message in e.messages:
                    messages.error(request, message)
                # keep what was entered so it can be corrected
                if isinstance(raw_rows, list):
                    submitted = {
                        str(row.get("id")): str(row.get("folio") or "")
                        for row in raw_rows
                        if isinstance(row, dict)
                    }
            else:
                if counts:
                    messages.success(
                        request,
                        f"Saved: linked {counts['linked']}, unlinked "
                        f"{counts['unlinked']}, and created {counts['created']} "
                        f"new folio record{'' if counts['created'] == 1 else 's'}.",
                    )
                    if created:
                        messages.warning(
                            request,
                            format_html(
                                "Add a line range to the new folio records so "
                                "the text can turn to them: {}",
                                format_html_join(
                                    ", ",
                                    '<a href="{}">{}</a>',
                                    (
                                        (
                                            reverse(
                                                "admin:manuscript_folio_change",
                                                args=[folio.pk],
                                            ),
                                            folio.folio_number,
                                        )
                                        for folio in created
                                    ),
                                ),
                            ),
                        )
                else:
                    messages.info(request, "No changes to save.")
                return redirect(request.path)

        folios = manuscript.folio_set.annotate(
            toponym_count=Count("locationalias", distinct=True)
        )
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": f"Link IIIF canvases: {manuscript}",
            "manuscript": manuscript,
            "change_url": change_url,
            "can_create": can_create,
            "folios": [
                {
                    "id": folio.pk,
                    "number": folio.folio_number or "",
                    "canvas_id": folio.canvas_id,
                    "line_start": folio.line_code_range_start,
                    "line_end": folio.line_code_range_end,
                    "toponyms": folio.toponym_count,
                    "admin_url": reverse(
                        "admin:manuscript_folio_change", args=[folio.pk]
                    ),
                }
                for folio in folios
            ],
            "submitted": submitted,
        }
        return TemplateResponse(
            request, "admin/manuscript/singlemanuscript/link_canvases.html", context
        )

    class Media:
        js = ("js/text_annotations.js",)
        css = {"all": ("css/text_annotator.css",)}

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("family")


@admin.register(Folio)
class FolioAdmin(ImportExportModelAdmin):
    resource_class = FolioResource
    form = FolioAdminForm

    list_display = [
        "folio_display",
        "folio_number",
        "canvas_label",
        "line_range_display",
        "stanza_count",
        "toponym_count",
    ]
    list_select_related = ["manuscript"]
    ordering = ["manuscript__siglum", "folio_number"]
    list_filter = ["manuscript", ("canvas_id", admin.EmptyFieldListFilter)]
    search_fields = [
        "folio_number",
        "manuscript__siglum",
        "line_code_range_start",
        "line_code_range_end",
        "canvas_label",
    ]

    readonly_fields = [
        "stanza_list",
        "line_range_display",
        "stanza_count",
        "linked_image",
        "canvas_index",
        "canvas_label",
        "image_id",
        "toponym_list",
    ]

    fieldsets = (
        ("Folio Information", {"fields": ("manuscript", "folio_number")}),
        (
            "IIIF Canvas",
            {
                # the linked image shows the canvas position, counting from 1
                "fields": ("linked_image", "canvas_id", "canvas_label", "image_id"),
            },
        ),
        (
            "Line Range",
            {
                "fields": (
                    "line_code_range_start",
                    "line_code_range_end",
                    "line_range_display",
                )
            },
        ),
        (
            "Associated Stanzas",
            {
                "fields": ("stanza_count", "stanza_list"),
            },
        ),
        ("Toponyms", {"fields": ("toponym_list",)}),
        ("Notes", {"fields": ("folio_includes_map", "folio_notes", "public_note")}),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                ("Folio Information", {"fields": ("manuscript", "folio_number")}),
                (
                    "Line Range",
                    {"fields": ("line_code_range_start", "line_code_range_end")},
                ),
                (
                    "Notes",
                    {"fields": ("folio_includes_map", "folio_notes", "public_note")},
                ),
            )
        return self.fieldsets

    def get_queryset(self, request):
        return (
            super().get_queryset(request).annotate(toponym_total=Count("locationalias"))
        )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if (
            request.method == "POST"
            and object_id
            and "_rename_confirmed" not in request.POST
        ):
            response = self.rename_confirmation(request, object_id)
            if response:
                return response
        return super().changeform_view(request, object_id, form_url, extra_context)

    def rename_confirmation(self, request, object_id):
        """Toponyms are attached to the folio record, not its number, so renaming
        a record moves them too. Returns a page listing them to confirm against,
        or None if the submission has no such rename to confirm, leaving any
        errors to the usual change form."""
        folio = self.get_object(request, unquote(object_id))
        if folio is None or not self.has_change_permission(request, folio):
            return None
        toponyms = folio_toponym_rows(folio)
        if not toponyms:
            return None
        old_number = folio.folio_number
        form_class = self.get_form(request, folio, change=True)
        form = form_class(request.POST, request.FILES, instance=folio)
        if not form.is_valid() or "folio_number" not in form.changed_data:
            return None
        add_url = reverse("admin:manuscript_folio_add")
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "Are you sure?",
            "manuscript": folio.manuscript,
            "old_number": old_number,
            "new_number": form.cleaned_data["folio_number"],
            "toponyms": toponyms,
            "change_url": reverse("admin:manuscript_folio_change", args=[folio.pk]),
            "add_url": f"{add_url}?manuscript={folio.manuscript_id}",
            # resubmitted as they are, including which save button was used
            "hidden_fields": [
                (name, value)
                for name, values in request.POST.lists()
                if name != "csrfmiddlewaretoken"
                for value in values
            ],
        }
        return TemplateResponse(
            request, "admin/manuscript/folio/rename_confirmation.html", context
        )

    @admin.display(description="Toponyms", ordering="toponym_total")
    def toponym_count(self, obj):
        return folio_toponym_count(obj)

    @admin.display(description="Linked image")
    def linked_image(self, obj):
        if not obj.pk or not obj.manuscript_id:
            return "-"
        return linked_image_link(obj, thumbnail=True)

    @admin.display(description="Toponym aliases on this folio")
    def toponym_list(self, obj):
        if not obj.pk:
            return "-"
        rows = folio_toponym_rows(obj)
        if not rows:
            return "None"
        return format_html(
            '<div style="max-height: 400px; overflow-y: auto;">'
            '<table style="width: 100%;"><tr><th>Alias</th><th>Toponym</th></tr>'
            "{}</table></div>",
            format_html_join(
                "", '<tr><td><a href="{}">{}</a></td><td>{}</td></tr>', rows
            ),
        )

    def stanza_count(self, obj):
        return obj.stanzas.count()

    stanza_count.short_description = "Number of Stanzas"

    @admin.display(
        description="Folio",
        ordering=Concat("manuscript__siglum", Value(" "), "folio_number"),
    )
    def folio_display(self, obj):
        manuscript = obj.manuscript or "No manuscript"
        return f"{manuscript} · {obj.folio_number or '(no folio number)'}"

    def line_range_display(self, obj):
        if not obj.line_code_range_start:
            return "-"
        end = obj.line_code_range_end or "End"
        return f"{obj.line_code_range_start} → {end}"

    line_range_display.short_description = "Line Range"
    line_range_display.admin_order_field = "line_code_range_start"

    def stanza_list(self, obj):
        stanzas = obj.stanzas.order_by("stanza_line_code_starts")
        if not stanzas.exists():
            return "No stanzas associated"

        html = ['<div style="max-height: 400px; overflow-y: auto;">']
        html.append('<table style="width: 100%;">')
        html.append("<tr><th>Line Code</th><th>Text Preview</th></tr>")

        for stanza in stanzas:
            preview = (
                stanza.stanza_text[:100] + "..."
                if len(stanza.stanza_text) > 100
                else stanza.stanza_text
            )
            admin_link = reverse("admin:manuscript_stanza_change", args=(stanza.pk,))
            html.append(
                f"<tr>"
                f"""<td style="padding: 5px; border-bottom: 1px solid #eee;">
                    <a href="{admin_link}">{stanza.stanza_line_code_starts}</a>
                </td>"""
                f'<td style="padding: 5px; border-bottom: 1px solid #eee;">{preview}</td>'
                f"</tr>"
            )

        html.append("</table></div>")
        return format_html("".join(html))

    stanza_list.short_description = "Stanzas on this Folio"

    def has_delete_permission(self, request, obj=None):
        """Allow deletion but with a warning"""
        return True  # You might want to add a custom deletion warning/confirmation


class ReferenceAdmin(ImportExportModelAdmin):
    list_display = ("reference", "bert")
    resource_class = ReferenceResource


@admin.register(Library)
class LibraryAdmin(admin.ModelAdmin):
    list_display = ("library", "city", "id")
    list_filter = ("city",)


class CodexAdmin(admin.ModelAdmin):
    list_display = ("id", "support", "height", "folia", "date")


@admin.register(Location)
class LocationAdmin(ImportExportModelAdmin):
    resource_class = LocationResource
    list_display = (
        "placename_id",
        "name",
        "placename_ancient",
        "placename_modern",
        "toponym_type",
        "place_type",
        "slug",
        "id",
    )
    search_fields = ("placename_id", "description", "modern_country")
    list_filter = ("place_type", "modern_country", "toponym_type")
    inlines = [LocationAliasInline]

    def description_html(self, obj):
        return format_html(obj.description) if obj.description else ""

    description_html.short_description = "Description"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        instance = form.instance
        instance.geocode()

    def get_queryset(self, request):
        # prefetch folio_set for get_related_folios,
        # locationalias_set for the modern/mss placename methods
        return (
            super()
            .get_queryset(request)
            .prefetch_related("folio_set", "locationalias_set")
        )


@admin.register(LocationAlias)
class LocationAliasAdmin(ImportExportModelAdmin):
    resource_class = LocationAliasResource
    list_display = (
        "id",
        "placename_alias",
        "location",
        "location__name",
        "manuscript",
        "folio",
    )
    list_filter = ("location",)
    search_fields = ("id", "placename_alias",)


@admin.action(description="Set language of the selected stanza to Italian")
def set_language_to_italian(modeladmin, request, queryset):
    queryset.update(language="it")


@admin.action(description="Set language of the selected stanza to English")
def set_language_to_english(modeladmin, request, queryset):
    queryset.update(language="en")


class StanzaAdminForm(forms.ModelForm, StripDivMixin):
    class Meta:
        model = Stanza
        fields = "__all__"

    def clean_stanza_text(self):
        return self.strip_outer_div("stanza_text")


@admin.register(Stanza)
class StanzaAdmin(admin.ModelAdmin):
    form = StanzaAdminForm
    inlines = [
        EditorialNoteInline,
        CrossReferenceInline,
        TextualVariantInline,
    ]
    list_display = (
        "stanza_line_code_starts",
        "formatted_stanza_text",
        "language",
    )
    search_fields = (
        "stanza_text",
        "stanza_line_code_starts",
    )
    list_filter = ("language",)
    actions = [set_language_to_italian, set_language_to_english]
    autocomplete_fields = ("folios",)

    class Media:
        css = {
            "all": (
                "css/text_annotations.css",
                "fontawesomefree/css/fontawesome.css",
                "fontawesomefree/css/solid.css",
            )
        }
        js = ("js/text_annotations.js",)

    def formatted_stanza_text(self, obj):
        return format_html(obj.stanza_text)

    formatted_stanza_text.short_description = "Stanza Text"


class StanzaTranslatedAdminForm(forms.ModelForm, StripDivMixin):
    class Meta:
        model = StanzaTranslated
        fields = "__all__"

    def clean_stanza_text(self):
        return self.strip_outer_div("stanza_text")


@admin.register(StanzaTranslated)
class StanzaTranslatedAdmin(admin.ModelAdmin):
    form = StanzaTranslatedAdminForm
    list_display = ("stanza_line_code_starts", "stanza_text", "language")
    search_fields = ("stanza", "stanza_text")
    list_filter = ("language",)
    inlines = [EditorialNoteInline, CrossReferenceInline, TextualVariantInline]

    class Media:
        css = {
            "all": (
                "css/text_annotations.css",
                "fontawesomefree/css/fontawesome.css",
                "fontawesomefree/css/solid.css",
            )
        }
        js = ("js/text_annotations.js",)


@admin.register(LineCode)
class LineCodeAdmin(ImportExportModelAdmin):
    resource_class = LineCodeResource
    list_display = ("code", "get_toponyms", "get_folio")
    search_fields = ("code",)
    list_filter = ("associated_toponyms", "associated_folio__manuscript")
    filter_horizontal = ("associated_toponyms",)

    def get_toponyms(self, obj):
        return ", ".join(
            [toponym.placename_id for toponym in obj.associated_toponyms.all()]
        )

    def get_folio(self, obj):
        if obj.associated_folio:
            return f"{obj.associated_folio.manuscript.siglum}: {obj.associated_folio.folio_number}"
        return "-"

    get_toponyms.short_description = "Associated Toponyms (IDs)"
    get_folio.short_description = "Associated Folio"


@admin.register(ManuscriptFamily)
class ManuscriptFamilyAdmin(admin.ModelAdmin):
    list_display = ["name", "get_manuscript_count", "get_manuscripts"]
    autocomplete_fields = ["manuscripts"]
    search_fields = ["name"]

    def get_manuscript_count(self, obj):
        return obj.total_manuscripts

    get_manuscript_count.short_description = "Count"

    def get_manuscripts(self, obj):
        """Display associated manuscripts' sigla"""
        manuscripts = obj.manuscripts.all().order_by("siglum")
        return ", ".join([m.siglum for m in manuscripts])

    get_manuscripts.short_description = "Associated Manuscripts"

    def get_queryset(self, request):
        """Override for list view optimizations"""
        qs = super().get_queryset(request)
        # Prefetch for get_manuscripts
        return qs.prefetch_related("manuscripts").annotate(
            # Annotate for get_manuscript_count
            total_manuscripts=Count("manuscripts")
        )
