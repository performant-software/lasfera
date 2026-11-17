from bs4 import BeautifulSoup
from django import template
from django.utils.safestring import mark_safe
from django.utils.text import slugify

register = template.Library()

# Heading tags in rich text, and heading blocks (which render as a div with
# this class), with the level each counts as in the table of contents
HEADING_LEVELS = {"h2": 2, "h3": 3, "h4": 4}
HEADING_BLOCK_CLASS = "block-heading"


def heading_level(element):
    if element.name in HEADING_LEVELS:
        return HEADING_LEVELS[element.name]
    return 2


def nested_list(soup, headings, list_tag="ul"):
    """A list of links to the (level, text, id) headings, nested by level"""
    top = soup.new_tag(list_tag)
    lists = [[None, top]]  # [level of its items, list], innermost last
    for level, text, anchor in headings:
        while len(lists) > 1 and lists[-1][0] > level:
            lists.pop()
        if lists[-1][0] is None:
            lists[-1][0] = level
        elif level > lists[-1][0]:
            sublist = soup.new_tag(list_tag)
            items = lists[-1][1].find_all("li", recursive=False)
            (items[-1] if items else lists[-1][1]).append(sublist)
            lists.append([level, sublist])
        link = soup.new_tag("a", href=f"#{anchor}")
        link.string = text
        item = soup.new_tag("li")
        item.append(link)
        lists[-1][1].append(item)
    return top


@register.filter
def with_table_of_contents(html):
    """
    Give each heading in the page body HTML an id to link to, and fill in any
    table of contents blocks (templates/blocks/table_of_contents.html) with
    links to the headings. Headings inside accordions are left out, since
    they're hidden until opened.
    """
    soup = BeautifulSoup(html, "html.parser")
    elements = [
        element
        for element in soup.select(
            ", ".join([*HEADING_LEVELS, f".{HEADING_BLOCK_CLASS}"])
        )
        if not element.find_parent(["details", "nav"])
        and element.get_text(strip=True)
    ]
    if not elements:
        return html

    used_ids = {element["id"] for element in soup.select("[id]")}
    headings = []
    for element in elements:
        text = element.get_text(" ", strip=True)
        if not element.get("id"):
            base = slugify(text) or "section"
            anchor, n = base, 1
            while anchor in used_ids:
                n += 1
                anchor = f"{base}-{n}"
            element["id"] = anchor
            used_ids.add(anchor)
        headings.append((heading_level(element), text, element["id"]))

    for toc in soup.select("[data-toc]"):
        try:
            depth = int(toc.get("data-toc-depth"))
        except (TypeError, ValueError):
            depth = 3
        list_tag = "ol" if toc.has_attr("data-toc-numbered") else "ul"
        toc.append(
            nested_list(soup, [h for h in headings if h[0] <= depth], list_tag)
        )

    return mark_safe(str(soup))
