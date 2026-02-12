from wagtail.admin.panels import FieldPanel
from wagtail.contrib.routable_page.models import RoutablePageMixin, route
from wagtail.fields import RichTextField
from wagtail.models import Page
from wagtail.snippets.models import register_snippet
from django.db import models


class AboutPage(RoutablePageMixin, Page):
    body = RichTextField(blank=True)
    team = RichTextField(blank=True)

    content_panels = Page.content_panels + [
        FieldPanel("body", classname="full"),
        FieldPanel("team", classname="full"),
    ]
    template = "pages/about_page.html"


class SitePage(Page):
    body = RichTextField(blank=True)
    content_panels = Page.content_panels + [
        FieldPanel("body", classname="full"),
    ]
    template = "pages/site_page.html"


@register_snippet
class HomeIntroduction(models.Model):
    title = models.CharField(max_length=255)
    body = RichTextField()

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
