import uuid

from django.db import migrations
from django.db.models import JSONField
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils import timezone

SLUG = "how-to-use-the-gazetteer"
TITLE = "How to use the gazetteer"

# The help that was in templates/gazetteer/gazetteer_index.html, as rich text
HELP_TEXT = (
    f"<h2>{TITLE}</h2>"
    "<p>You can learn more about the toponyms in three ways:</p>"
    "<ol>"
    "<li>Select a toponym from the index list on the left. This list is "
    "filterable by fuzzy-matching search. Selecting a toponym will allow you to "
    "view more detailed information.</li>"
    "<li>Start typing a toponym in the search box, and the list will use fuzzy "
    "matching to offer you a smaller number of options.</li>"
    "<li>Select a point on the map to view the toponym associated with that "
    "location. You can then click on the toponym for more detailed "
    "information.</li>"
    "</ol>"
    "<p>With each toponym we have listed a few of the naming variants that "
    "appear across the Sfera manuscripts. Our list of variants is not "
    "comprehensive, and provides only a representative sample of the kinds of "
    "spelling variants found on Sfera maps. In particular, doubled letters "
    "(<b>angolo</b> &gt;&gt; <b>angollo</b>), <b>c/ch</b> and <b>g/gh</b> "
    "variants (&gt;&gt; <b>angholo</b>), and vowel variation (&gt;&gt; "
    "<b>angelo</b>) are so common that it is impossible to note all "
    "variations. Toponyms with few or no variants either (a) are so common as "
    "to acquire a standard spelling (e.g. <b>asia</b>) OR (b) do not often "
    "appear in the <i>Sfera</i> maps (e.g. <b>livorno</b>). Our list of "
    "variants expands abbreviations except in the case of labels such as "
    "<b>f[iume]</b> or <b>m[are]</b>, where variation is shown.</p>"
)

PATH_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PATH_STEP = 4


def next_child_path(parent_path, last_child_path):
    """The tree path for a page added after a parent's last child"""
    number = int(last_child_path[-PATH_STEP:], 36) + 1 if last_child_path else 1
    step = ""
    while number:
        number, digit = divmod(number, 36)
        step = PATH_ALPHABET[digit] + step
    return parent_path + step.rjust(PATH_STEP, "0")


def gazetteer_dropdown(items, gazetteer_url, help_page_pk):
    """
    The menu items with the top-level link to the gazetteer turned into a
    dropdown of it and its help page, or None if the menu has no such link
    """
    for index, item in enumerate(items):
        value = item.get("value", {})
        if item.get("type") == "link" and value.get("link_url") == gazetteer_url:
            links = [
                {"label": value["label"], "page": None, "link_url": gazetteer_url},
                {"label": TITLE, "page": help_page_pk, "link_url": ""},
            ]
            dropdown = {
                "type": "dropdown",
                "id": item.get("id") or str(uuid.uuid4()),
                "value": {
                    "label": value["label"],
                    "links": [
                        {"type": "item", "value": link, "id": str(uuid.uuid4())}
                        for link in links
                    ],
                },
            }
            return items[:index] + [dropdown] + items[index + 1 :]
    return None


def gazetteer_link(items, help_page_pk):
    """The menu items with the gazetteer dropdown turned back into a link"""
    for index, item in enumerate(items):
        links = item.get("value", {}).get("links", [])
        if item.get("type") == "dropdown" and any(
            link["value"].get("page") == help_page_pk for link in links
        ):
            others = [
                link["value"]
                for link in links
                if link["value"].get("page") != help_page_pk
            ]
            link = {
                "type": "link",
                "id": item["id"],
                "value": {**others[0], "label": item["value"]["label"]},
            }
            return items[:index] + [link] + items[index + 1 :]
    return None


def add_help_page(apps, schema_editor):
    """
    Move the gazetteer's help into a CMS page at the top of the site, and list
    it with the gazetteer in a dropdown in the navigation menu
    """
    Site = apps.get_model("wagtailcore", "Site")
    Page = apps.get_model("wagtailcore", "Page")
    SitePage = apps.get_model("pages", "SitePage")
    ContentType = apps.get_model("contenttypes", "ContentType")
    NavigationMenu = apps.get_model("pages", "NavigationMenu")

    site = Site.objects.filter(is_default_site=True).first()
    if not site or Page.objects.filter(slug=SLUG).exists():
        return
    parent = Page.objects.get(pk=site.root_page_id)
    last_child = (
        Page.objects.filter(path__startswith=parent.path, depth=parent.depth + 1)
        .order_by("-path")
        .first()
    )
    now = timezone.now()
    page = SitePage.objects.create(
        title=TITLE,
        draft_title=TITLE,
        slug=SLUG,
        content_type=ContentType.objects.get_for_model(SitePage),
        path=next_child_path(parent.path, last_child.path if last_child else None),
        depth=parent.depth + 1,
        numchild=0,
        url_path=f"{parent.url_path}{SLUG}/",
        locale_id=parent.locale_id,
        live=True,
        has_unpublished_changes=False,
        first_published_at=now,
        last_published_at=now,
        body=[{"type": "paragraph", "value": HELP_TEXT, "id": str(uuid.uuid4())}],
    )
    parent.numchild += 1
    parent.save(update_fields=["numchild"])

    menu = NavigationMenu.objects.annotate(raw_items=Cast("items", JSONField())).first()
    if menu:
        items = gazetteer_dropdown(menu.raw_items or [], reverse("toponyms"), page.pk)
        if items:
            menu.items = items
            menu.save(update_fields=["items"])


def remove_help_page(apps, schema_editor):
    Page = apps.get_model("wagtailcore", "Page")
    NavigationMenu = apps.get_model("pages", "NavigationMenu")

    page = Page.objects.filter(slug=SLUG).order_by("depth").first()
    if not page:
        return
    menu = NavigationMenu.objects.annotate(raw_items=Cast("items", JSONField())).first()
    if menu:
        items = gazetteer_link(menu.raw_items or [], page.pk)
        if items:
            menu.items = items
            menu.save(update_fields=["items"])
    parent = Page.objects.get(path=page.path[:-PATH_STEP])
    page.delete()
    parent.numchild -= 1
    parent.save(update_fields=["numchild"])


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0016_layout_blocks"),
        ("wagtailcore", "0094_alter_page_locale"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(add_help_page, remove_help_page),
    ]
