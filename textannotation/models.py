from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.template.defaultfilters import truncatechars
from django.utils.html import strip_tags

from html import unescape
from prose.fields import RichTextField

from manuscript.models import SingleManuscript


class BaseAnnotation(models.Model):
    """Abstract base class. Defines fields for annotations on specific text
    selections within a ProseField.
    All annotations belong to one of the subtype classes."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    # Store the text position data
    from_pos = models.JSONField(
        help_text="ProseMirror position data for annotation start", default=dict
    )
    to_pos = models.JSONField(
        help_text="ProseMirror position data for annotation end", default=dict
    )
    selected_text = models.TextField(default="")
    annotation = RichTextField(
        help_text="Enter your annotation here", blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return self.selected_text

    @property
    def excerpt(self):
        # Truncated annotation content for admin list view
        return unescape(truncatechars(strip_tags(self.annotation), 48))

    @property
    def annotation_type(self):
        """
        Returns the shorthand annotation type for the inheriting models.
        """
        if isinstance(self, EditorialNote):
            return "note"
        if isinstance(self, CrossReference):
            return "reference"
        if isinstance(self, TextualVariant):
            return "variant"
        return "unknown"


class EditorialNote(BaseAnnotation):
    """An annotation of type Editorial Note"""


class CrossReference(BaseAnnotation):
    """An annotation of type Cross Reference"""


class TextualVariant(BaseAnnotation):
    """An annotation of type Textual Variant, with additional metadata"""

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(significance__in=[0, 1, 2, 3]),
                name="significance_valid_range",
            )
        ]

    annotation = RichTextField(
        "Variant text",
        blank=True,
        null=True,
    )
    variant_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="Unique identifier for each variant",
    )
    manuscript = models.ForeignKey(
        SingleManuscript,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Manuscript (siglum)",
    )
    # significance can be 0, 1, 2, 3
    SIGNIFICANCE_CHOICES = [(i, str(i)) for i in range(4)]
    significance = models.PositiveSmallIntegerField(
        choices=SIGNIFICANCE_CHOICES, default=0
    )
    notes = RichTextField(blank=True, null=True)

    editor_initials = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return self.annotation
