from wagtail.admin.panels import FieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, route
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page
from wagtail.snippets.models import register_snippet
from django.db import models

from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock
from wagtail.embeds.blocks import EmbedBlock


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock(required=True)
    caption = blocks.CharBlock(
        required=False, help_text="Optional caption for the image"
    )

    class Meta:
        icon = "image"
        template = "partials/image_block.html"


class CommonContentBlock(blocks.StreamBlock):
    paragraph = blocks.RichTextBlock(icon="pilcrow")
    heading = blocks.CharBlock(icon="title")
    image = ImageBlock()
    video = EmbedBlock(icon="media", max_width=800, max_height=400)


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


@register_snippet
class HomeIntroduction(models.Model):
    title = models.CharField(max_length=255)
    body = StreamField(CommonContentBlock(), use_json_field=True, blank=True)

    panels = [
        FieldPanel("title"),
        FieldPanel("body"),
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
