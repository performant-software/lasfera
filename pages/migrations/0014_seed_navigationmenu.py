import uuid

from django.db import migrations
from django.urls import reverse


def link(Page, label, slug=None, url=None):
    """A menu link to the CMS page with this slug, or to a URL"""
    value = {"label": label, "page": None, "link_url": ""}
    page = Page.objects.filter(slug=slug).order_by("depth").first() if slug else None
    if page:
        value["page"] = page.pk
    else:
        value["link_url"] = url or f"/{slug}/"
    return value


def seed_menu(apps, schema_editor):
    """Fill the menu with the links that were hard-coded in the navbar template"""
    NavigationMenu = apps.get_model("pages", "NavigationMenu")
    Page = apps.get_model("wagtailcore", "Page")

    def item(block_type, value):
        return {"type": block_type, "value": value, "id": str(uuid.uuid4())}

    def list_item(value):
        return {"type": "item", "value": value, "id": str(uuid.uuid4())}

    menu = NavigationMenu.objects.first() or NavigationMenu()
    if menu.items:
        return
    menu.items = [
        item("link", link(Page, "Introduction", slug="introduction")),
        item(
            "link",
            link(
                Page,
                "Edition",
                url=reverse("manuscript_stanzas", kwargs={"siglum": "Urb1"}),
            ),
        ),
        item("link", link(Page, "Gazetteer", url=reverse("toponyms"))),
        item("link", link(Page, "Manuscripts", url=reverse("manuscripts"))),
        item("link", link(Page, "Gallery", slug="gallery")),
        item(
            "dropdown",
            {
                "label": "Resources",
                "links": [
                    list_item(
                        link(Page, "La Sfera in the Classroom", slug="education")
                    ),
                    list_item(link(Page, "Data", slug="data")),
                    list_item(
                        link(Page, "Talks & Presentations", slug="talks-presentations")
                    ),
                ],
            },
        ),
        item("link", link(Page, "About", slug="about")),
    ]
    menu.save()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0013_navigationmenu"),
        ("wagtailcore", "0094_alter_page_locale"),
    ]

    operations = [
        migrations.RunPython(seed_menu, migrations.RunPython.noop),
    ]
