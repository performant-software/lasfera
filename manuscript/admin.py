from django import forms
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.urls import reverse
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from common.admin import StripDivMixin
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
from textannotation.admin import (
    CrossReferenceAdminForm,
    EditorialNoteAdminForm,
    TextualVariantAdminForm,
)
from textannotation.models import CrossReference, EditorialNote, TextualVariant


# Inline models --------------------------------------------
class StanzaInline(admin.StackedInline):
    model = Stanza
    extra = 1
    fields = (
        "stanza_line_code_starts",
        "stanza_line_code_ends",
        "stanza_text",
        "stanza_notes",
    )


class FolioInline(admin.StackedInline):
    model = Folio
    classes = ("collapse",)
    extra = 1


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
    autocomplete_fields = ("manuscripts", "folios")


class AuthorityFileInline(admin.TabularInline):
    model = AuthorityFile
    extra = 1


class EditorialNoteInline(GenericTabularInline):
    model = EditorialNote
    extra = 0
    fields = ("selected_text", "annotation")
    readonly_fields = ("selected_text",)
    form = EditorialNoteAdminForm


class CrossReferenceInline(GenericTabularInline):
    model = CrossReference
    extra = 0
    fields = ("selected_text", "annotation")
    readonly_fields = ("selected_text",)
    form = CrossReferenceAdminForm


class TextualVariantInline(GenericTabularInline):
    model = TextualVariant
    extra = 0
    fields = (
        "selected_text",
        "annotation",
        "manuscript",
        "significance",
        "notes",
        "variant_id",
        "editor_initials",
    )
    readonly_fields = ("selected_text",)
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


# Custom admin models --------------------------------------------
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

    @admin.display(boolean=True, description="IIIF Available")
    def has_iiif_url(self, obj):
        return bool(obj.iiif_url)

    class Media:
        js = ("js/text_annotations.js",)
        css = {"all": ("css/text_annotator.css",)}


class FolioAdmin(ImportExportModelAdmin):
    resource_class = FolioResource

    list_display = ["manuscript", "folio_number", "line_range_display", "stanza_count"]
    list_filter = ["manuscript"]
    search_fields = [
        "folio_number",
        "manuscript__siglum",
        "line_code_range_start",
        "line_code_range_end",
    ]

    readonly_fields = ["stanza_list", "line_range_display", "stanza_count"]

    fieldsets = (
        ("Folio Information", {"fields": ("manuscript", "folio_number")}),
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
    )

    def stanza_count(self, obj):
        return obj.stanzas.count()

    stanza_count.short_description = "Number of Stanzas"

    def line_range_display(self, obj):
        end = obj.line_code_range_end or "End"
        return f"{obj.line_code_range_start} → {end}"

    line_range_display.short_description = "Line Range"

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
            html.append(
                f"<tr>"
                f'<td style="padding: 5px; border-bottom: 1px solid #eee;">{stanza.stanza_line_code_starts}</td>'
                f'<td style="padding: 5px; border-bottom: 1px solid #eee;">{preview}</td>'
                f"</tr>"
            )

        html.append("</table></div>")
        return format_html("".join(html))

    stanza_list.short_description = "Stanzas on this Folio"

    def has_add_permission(self, request):
        """Disable manual adding - folios should be created via import"""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion but with a warning"""
        return True  # You might want to add a custom deletion warning/confirmation


class ReferenceAdmin(ImportExportModelAdmin):
    list_display = ("reference", "bert")
    resource_class = ReferenceResource


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
        "get_placename_modern",
        "get_mss_placename",
        "toponym_type",
        "place_type",
        "get_related_folios",
        "id",
    )
    search_fields = ("placename_id", "description", "modern_country")
    list_filter = ("place_type", "modern_country", "toponym_type")
    inlines = [LocationAliasInline]

    def description_html(self, obj):
        return format_html(obj.description) if obj.description else ""

    description_html.short_description = "Description"

    def get_related_folios(self, obj):
        return ", ".join([str(folio.folio_number) for folio in obj.folio_set.all()])

    get_related_folios.short_description = "Related folio"

    def get_placename_modern(self, obj):
        # use prefetched LocationAlias set
        alias = (
            obj.locationalias_set.all()[0] if obj.locationalias_set.exists() else None
        )
        return alias.placename_modern if alias else None

    get_placename_modern.short_description = "Modern Placename"

    def get_mss_placename(self, obj):
        alias = (
            obj.locationalias_set.all()[0] if obj.locationalias_set.exists() else None
        )
        return alias.placename_from_mss if alias else None

    get_mss_placename.short_description = "Manuscript Placename"

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
        "location",
        "placename_alias",
        "placename_from_mss",
        "placename_ancient",
        "placename_standardized",
    )
    list_filter = ("location",)
    search_fields = ("placename_alias",)
    raw_id_fields = ("location",)


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


admin.site.register(LineCode, LineCodeAdmin)

admin.site.register(Library, LibraryAdmin)
admin.site.register(Folio, FolioAdmin)
admin.site.register(SingleManuscript, SingleManuscriptAdmin)
admin.site.register(Stanza, StanzaAdmin)
admin.site.register(StanzaTranslated, StanzaTranslatedAdmin)

admin.site.site_header = "La Sfera Admin"
admin.site.site_title = "La Sfera Admin Portal"
admin.site.index_title = "Welcome to the La Sfera Manuscript Portal"
