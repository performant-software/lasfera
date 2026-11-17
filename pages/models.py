from django.core.files.storage import default_storage
from django.db import models
from wagtail import blocks
from django.core.exceptions import ValidationError
from wagtail.admin.panels import FieldPanel
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.contrib.routable_page.models import RoutablePageMixin
from wagtail.contrib.settings.models import BaseGenericSetting, register_setting
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images import get_image_model
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page
from wagtail.snippets.models import register_snippet


# Content shown in the previews in the CMS's "+" menu of blocks (see
# templates/wagtailcore/shared/block_preview.html)
PREVIEW_TEXT = (
    "<p>Dati's poem describes the heavens in its first book before turning to "
    "the lands and seas of the known world. The manuscripts differ widely in "
    "their maps, their marginal notes and the order of the stanzas.</p>"
)


def preview_images(count):
    """The most recently added images in the media library, for block previews"""
    return list(get_image_model().objects.order_by("-pk")[:count])


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock(required=True)
    caption = blocks.CharBlock(
        required=False, help_text="Optional caption for the image"
    )
    alt_text = blocks.CharBlock(
        required=False,
        help_text="Describe the image for screen readers. Defaults to the image title.",
    )
    # partials/image_block.html still handles the "left" and "right" values
    # this offered before Image + text, so any images using them still show
    alignment = blocks.ChoiceBlock(
        choices=[
            ("center", "Centered (default size)"),
            ("full", "Full width"),
        ],
        default="center",
        required=False,
        help_text="For an image with text beside it, use the Image + text block",
    )

    def get_preview_value(self):
        images = preview_images(1)
        return self.normalize(
            {
                "image": images[0] if images else None,
                "caption": images[0].title if images else "",
                "alignment": "center",
            }
        )

    class Meta:
        icon = "image"
        template = "partials/image_block.html"
        group = "Images and video"
        description = "An image with a caption, on its own line"

class AccordionBlock(blocks.StructBlock):
    title = blocks.CharBlock(required=True)
    content = blocks.RichTextBlock(required=True)

    class Meta:
        template = "blocks/accordion.html"
        icon = "arrow-down"
        label = "Accordion"
        group = "Page layout"
        description = "A heading that readers click to show or hide the text beneath it"
        preview_value = {"title": "Notes on the manuscripts", "content": PREVIEW_TEXT}


class QuoteBlock(blocks.StructBlock):
    text = blocks.RichTextBlock(
        features=[
            "bold",
            "italic",
            "superscript",
            "subscript",
            "strikethrough",
            "link",
            "document-link",
        ]
    )
    attribution = blocks.CharBlock(
        required=False,
        help_text="Optional: who said or wrote it, and where, shown beneath the "
        "quote (e.g. Goro Dati, History of Florence)",
    )

    class Meta:
        template = "blocks/quote.html"
        icon = "openquote"
        label = "Quote"
        group = "Text"
        description = "A quotation set apart from the text, with an optional attribution beneath it"
        preview_value = {
            "text": "<p>Through Sicily the poet turns his course, and names the "
            "cities one by one along the shore.</p>",
            "attribution": "Goro Dati, La Sfera",
        }


class TableOfContentsBlock(blocks.StructBlock):
    """
    Links to the headings on the page, which are filled in when the page is
    rendered (see pages/templatetags/table_of_contents.py)
    """

    title = blocks.CharBlock(required=False, default="Table of Contents")
    depth = blocks.ChoiceBlock(
        choices=[
            ("2", "Main headings only"),
            ("3", "Main headings and subheadings"),
            ("4", "All headings"),
        ],
        default="3",
        help_text="Which levels of heading to list",
    )
    collapsible = blocks.BooleanBlock(
        required=False,
        default=True,
        help_text="Hide the list until the reader opens it, like an accordion",
    )
    style = blocks.ChoiceBlock(
        choices=[
            ("simple", "Simple list"),
            ("boxed", "In a shaded box"),
            ("margin", "In the left margin"),
        ],
        default="simple",
        help_text="How the list is displayed. \"In the left margin\" keeps the "
        "list beside the text as the reader scrolls on wide screens; on narrower "
        "screens, or pages with a sidebar, it's shown within the text like a "
        "simple list.",
    )
    size = blocks.ChoiceBlock(
        choices=[("normal", "Normal"), ("small", "Small")],
        default="normal",
        label="Text size",
    )
    numbered = blocks.BooleanBlock(
        required=False,
        default=False,
        help_text="Number the headings: 1, 1.1, 1.2, 2…",
    )
    bold_main_headings = blocks.BooleanBlock(
        required=False,
        default=True,
        help_text="Show the main headings in bold",
    )

    class Meta:
        template = "blocks/table_of_contents.html"
        icon = "list-ol"
        label = "Table of contents"
        group = "Page layout"
        description = "A list of links to the headings on the page, filled in automatically"
        # shown open, above sample headings (see the preview template)
        preview_template = "blocks/previews/table_of_contents.html"
        preview_value = {
            "title": "Table of Contents",
            "depth": "3",
            "collapsible": False,
            "style": "simple",
            "size": "normal",
            "numbered": False,
            "bold_main_headings": True,
        }


class ImageTextBlock(blocks.StructBlock):
    """An image with text beside it; the next block always starts below the image"""

    image = ImageChooserBlock(required=True)
    caption = blocks.CharBlock(required=False)
    alt_text = blocks.CharBlock(
        required=False,
        help_text="Describe the image for screen readers. Defaults to the image title.",
    )
    image_side = blocks.ChoiceBlock(
        choices=[("left", "Left"), ("right", "Right")], default="left"
    )
    image_width = blocks.ChoiceBlock(
        choices=[("third", "A third of the page"), ("half", "Half the page")],
        default="third",
        help_text="On phones the image is shown full width above the text",
    )
    # no images or embeds in the text, so the block's own image is the only float
    text = blocks.RichTextBlock(
        features=[
            "h2",
            "h3",
            "h4",
            "bold",
            "italic",
            "superscript",
            "subscript",
            "strikethrough",
            "ol",
            "ul",
            "blockquote",
            "link",
            "document-link",
        ]
    )

    def get_preview_value(self):
        images = preview_images(1)
        return self.normalize(
            {
                "image": images[0] if images else None,
                "caption": images[0].title if images else "",
                "image_side": "left",
                "image_width": "third",
                "text": PREVIEW_TEXT * 2,
            }
        )

    class Meta:
        template = "blocks/image_text.html"
        icon = "image"
        label = "Image + text"
        group = "Images and video"
        description = "An image with text beside it. The next block always starts below the image."


class ImageRowItemBlock(blocks.StructBlock):
    image = ImageChooserBlock(required=True)
    caption = blocks.CharBlock(required=False)
    alt_text = blocks.CharBlock(
        required=False,
        help_text="Describe the image for screen readers. Defaults to the image title.",
    )

    class Meta:
        icon = "image"
        label = "Image"


class ImageRowBlock(blocks.StructBlock):
    """Several images side by side, or one at a time in a carousel"""

    images = blocks.ListBlock(ImageRowItemBlock(), min_num=2)
    display = blocks.ChoiceBlock(
        choices=[("row", "Row"), ("carousel", "Carousel")],
        default="row",
        label="Display as",
        help_text="A row shows every image at once, up to four across. A carousel "
        "shows one at a time, with arrows to move between them.",
    )

    def get_preview_value(self):
        return self.normalize(
            {
                "images": [
                    {"image": image, "caption": image.title}
                    for image in preview_images(2)
                ],
                "display": "row",
            }
        )

    class Meta:
        template = "blocks/image_row.html"
        icon = "image"
        label = "Image row"
        group = "Images and video"
        description = "Two or more images side by side to compare, or shown one at a time as a carousel"


class DividerBlock(blocks.StructBlock):
    """Makes the text after it start below an image, rather than beside it"""

    show_line = blocks.BooleanBlock(
        required=False,
        default=False,
        help_text="Draw a thin line across the page",
    )

    class Meta:
        template = "blocks/divider.html"
        icon = "minus"
        label = "Divider"
        help_text = "The text after the divider starts below the image, rather than beside it."
        group = "Page layout"
        description = "Makes the text after it start below an image, rather than beside it. Can also show a line."
        # shown between text wrapping around an image and text below it
        preview_template = "blocks/previews/divider.html"
        preview_value = {"show_line": True}


class CommonContentBlock(blocks.StreamBlock):
    # listed in the "+" menu in this order, under their groups
    paragraph = blocks.RichTextBlock(
        icon="pilcrow",
        group="Text",
        description="Text with formatting, links and lists",
        preview_value=PREVIEW_TEXT,
    )
    heading = blocks.CharBlock(
        icon="title",
        group="Text",
        description="A section heading, listed in the table of contents",
        preview_value="Book III: The islands of the Mediterranean",
    )
    quote = QuoteBlock()
    image = ImageBlock()
    image_text = ImageTextBlock()
    image_row = ImageRowBlock()
    video = EmbedBlock(
        icon="media",
        max_width=800,
        max_height=400,
        group="Images and video",
        description="A video from YouTube or Vimeo, added by its web address",
    )
    divider = DividerBlock()
    accordion = AccordionBlock()
    table_of_contents = TableOfContentsBlock()

    def sorted_child_blocks(self):
        # keep the order above, rather than sorting the groups alphabetically
        return list(self.child_blocks.values())

class AboutPage(RoutablePageMixin, Page):
    body = StreamField(CommonContentBlock(), use_json_field=True, blank=True)
    team = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("body", classname="full"),
        FieldPanel("team", classname="full"),
    ]
    template = "pages/about_page.html"


class SitePage(Page):
    body = StreamField(CommonContentBlock(), use_json_field=True, blank=True)
    content_panels = Page.content_panels + [
        FieldPanel("body", classname="full"),
    ]
    template = "pages/site_page.html"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        # The first table of contents set to go in the left margin, which
        # site_page.html puts in a column beside the text on wide screens
        context["margin_toc"] = next(
            (
                block
                for block in self.body
                if block.block_type == "table_of_contents"
                and block.value["style"] == "margin"
            ),
            None,
        )
        return context


class NavCardBlock(blocks.StructBlock):
    title = blocks.CharBlock(
        required=True,
        help_text="The title text that will appear in the card (e.g. Edition)",
    )
    description = blocks.TextBlock(
        required=True, help_text="The subtitle text that will appear in the card"
    )
    image = ImageChooserBlock(required=True)
    url = blocks.CharBlock(required=True, help_text="The URL for the 'More' link")

    class Meta:
        icon = "link"
        label = "Navigation Card"


class NavLinkValue(blocks.StructValue):
    def url(self):
        page = self.get("page")
        return page.url if page else self.get("link_url")


class NavLinkBlock(blocks.StructBlock):
    """A navigation menu link, to either a CMS page or any other URL"""

    label = blocks.CharBlock(required=True, help_text="The text shown in the menu")
    page = blocks.PageChooserBlock(
        required=False, help_text="Link to a page created in the CMS..."
    )
    link_url = blocks.CharBlock(
        required=False,
        label="URL",
        help_text="...or to any other address, e.g. /manuscripts/ for a page on "
        "this site or https://example.com for another site",
    )

    def clean(self, value):
        value = super().clean(value)
        if bool(value.get("page")) == bool(value.get("link_url")):
            message = "Choose a page or enter a URL (but not both)."
            raise StructBlockValidationError(
                block_errors={
                    "page": ValidationError(message),
                    "link_url": ValidationError(message),
                }
            )
        return value

    class Meta:
        icon = "link"
        label = "Link"
        value_class = NavLinkValue


class NavDropdownBlock(blocks.StructBlock):
    """A navigation menu heading that opens a list of links"""

    label = blocks.CharBlock(required=True, help_text="The text shown in the menu")
    links = blocks.ListBlock(NavLinkBlock(), min_num=1)

    class Meta:
        icon = "list-ul"
        label = "Dropdown"


@register_setting(icon="list-ul")
class NavigationMenu(BaseGenericSetting):
    """The site's top navigation bar, editable under Settings in the CMS"""

    items = StreamField(
        [
            ("link", NavLinkBlock()),
            ("dropdown", NavDropdownBlock()),
        ],
        use_json_field=True,
        blank=True,
        help_text="The items in the navigation bar, from left to right. Use a "
        "dropdown to group several links under one heading.",
    )

    panels = [FieldPanel("items")]

    class Meta:
        verbose_name = "Navigation menu"


@register_snippet
class HomeIntroduction(models.Model):
    title = models.CharField(max_length=255)
    body = StreamField(CommonContentBlock(), use_json_field=True, blank=True)
    navigation_cards = StreamField(
        [("card", NavCardBlock())],
        use_json_field=True,
        blank=True,
        help_text="The cards with links that appear below the intro text",
    )

    panels = [
        FieldPanel("title"),
        FieldPanel("body"),
        FieldPanel("navigation_cards"),
    ]

    def __str__(self):
        return self.title


@register_snippet
class ManuscriptsIntroduction(models.Model):
    title = models.CharField(max_length=255)
    body = RichTextField()

    panels = [
        FieldPanel("title"),
        FieldPanel("body"),
    ]

    def __str__(self):
        return self.title


class ExternalLinkBlock(blocks.StructBlock):
    """Block for adding external links to the data page"""

    title = blocks.CharBlock(required=True, help_text="Text to display for the link")
    url = blocks.URLBlock(required=True, label="URL")

    class Meta:
        icon = "link"
        label = "External Link"


class DocumentResourceBlock(blocks.StructBlock):
    """Block for adding document uploads to the data page"""

    title = blocks.CharBlock(
        required=False, help_text="Optional: Override the document's original filename"
    )
    document = DocumentChooserBlock(required=True)

    class Meta:
        icon = "doc-empty"
        label = "Uploaded File (PDF, etc.)"


class DataPage(SitePage):
    """Page type used only for the Data page"""

    template = "pages/data_page.html"

    additional_resources = StreamField(
        [
            ("link", ExternalLinkBlock()),
            ("document", DocumentResourceBlock()),
        ],
        use_json_field=True,
        blank=True,
    )

    content_panels = SitePage.content_panels + [
        FieldPanel("additional_resources", heading="Additional Resources"),
    ]

    def get_context(self, request):
        """add our public export URLs to context to include in the template"""
        context = super().get_context(request)
        files = [
            ("Manuscripts", "manuscripts"),
            ("Folios", "folios"),
            ("Stanzas (Italian)", "stanzas"),
            ("Stanzas (English)", "translated_stanzas"),
            ("Textual Variants", "textual_variants"),
            ("Toponyms", "toponyms"),
            ("Toponym Variants", "toponym_variants"),
        ]
        export_list = []
        for label, slug in files:
            file_path = f"exports/{slug}.csv"
            # Use default_storage to generate the safe S3 URL
            # Fallback to '#' if the file hasn't been generated by the command yet
            if default_storage.exists(file_path):
                file_url = default_storage.url(file_path)
                export_list.append(
                    {
                        "label": label,
                        "csv": file_url,
                    }
                )
        context["exports"] = export_list
        return context
