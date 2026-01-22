from django import forms
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from common.admin import StripDivMixin
from textannotation.models import (
    CrossReference,
    EditorialNote,
    TextualVariant,
)
from textannotation.resources import TextualVariantResource


class AnnotatedContentTypeFilter(admin.SimpleListFilter):
    """Sidebar filter for annotations by annotated content type"""

    title = "annotated type"
    parameter_name = "content_type_id"

    def lookups(self, request, model_admin):
        # filter the options in the list by which ContentTypes have
        # actually been annotated
        annotated_cts = model_admin.model.objects.values_list(
            "content_type_id", flat=True
        ).distinct()
        content_types = ContentType.objects.filter(id__in=annotated_cts)

        # list filters require tuples like (id, label)
        return [
            (ct.id, ct.model_class()._meta.verbose_name.title())
            for ct in content_types
            if ct.model_class()
        ]

    def queryset(self, request, queryset):
        # filter the queryset by the selected value
        if self.value():
            return queryset.filter(content_type_id=self.value())
        return queryset


class BaseAnnotationAdminMixin:
    """Admin mixin for the BaseAnnotation models"""

    readonly_fields = ("line_code_display", "selected_text", "from_pos", "to_pos")
    list_display = (
        "selected_text",
        "line_code_display",
        "excerpt",
        "annotated_type",
        "created_at",
    )
    list_filter = (AnnotatedContentTypeFilter,)
    search_fields = (
        "selected_text",
        "stanza__stanza_line_code_starts",
        "stanza_translated__stanza_line_code_starts",
    )

    @admin.display(ordering="content_type")
    def annotated_type(self, obj):
        # Label for content type column, for display and sorting
        return obj.content_type.model_class()._meta.verbose_name.title()

    @admin.display(description="Line code", ordering="line_code")
    def line_code_display(self, obj):
        """Display the related line code in the list view and change
        views for annotations, if available"""
        target = obj.content_object

        if target and hasattr(target, "stanza_line_code_starts"):
            # generate a link to the change view for the stanza/stanzatranslated
            app_label = target._meta.app_label
            model_name = target._meta.model_name
            url = reverse(f"admin:{app_label}_{model_name}_change", args=[target.id])
            return format_html(
                '<a href="{}">{}</a>', url, target.stanza_line_code_starts
            )

        return "N/A"

    def get_queryset(self, request):
        # include prefetching for performance
        return (
            super()
            .get_queryset(request)
            .select_related("content_type")
            .prefetch_related("content_object")
            .annotate(
                # annotate with line code from stanza or stanzatranslated, for
                # combined sorting
                line_code=Coalesce(
                    "stanza__stanza_line_code_starts",
                    "stanza_translated__stanza_line_code_starts",
                )
            )
        )


class TextualVariantAdminForm(forms.ModelForm, StripDivMixin):
    class Meta:
        model = TextualVariant
        fields = "__all__"

    def clean_notes(self):
        return self.strip_outer_div("notes")

    def clean_annotation(self):
        return self.strip_outer_div("annotation")


@admin.register(TextualVariant)
class TextualVariantAdmin(BaseAnnotationAdminMixin, ImportExportModelAdmin):
    form = TextualVariantAdminForm
    resource_class = TextualVariantResource
    list_display = (
        "variant_id",
        "manuscript",
        "significance",
        "excerpt",
        "selected_text",
    )
    readonly_fields = ("line_code_display", "selected_text", "from_pos", "to_pos")

    @admin.display
    def variant_text(self, obj):
        return obj.annotation


class CrossReferenceAdminForm(forms.ModelForm, StripDivMixin):
    class Meta:
        model = CrossReference
        fields = "__all__"

    def clean_annotation(self):
        return self.strip_outer_div("annotation")


@admin.register(CrossReference)
class CrossReferenceAdmin(BaseAnnotationAdminMixin, admin.ModelAdmin):
    form = CrossReferenceAdminForm


class EditorialNoteAdminForm(forms.ModelForm, StripDivMixin):
    class Meta:
        model = EditorialNote
        fields = "__all__"

    def clean_annotation(self):
        return self.strip_outer_div("annotation")


@admin.register(EditorialNote)
class EditorialNoteAdmin(BaseAnnotationAdminMixin, admin.ModelAdmin):
    form = EditorialNoteAdminForm
