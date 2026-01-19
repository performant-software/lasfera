# templatetags/stanza_tags.py
import logging

from bs4 import BeautifulSoup
from django import template
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)
register = template.Library()


@register.filter
def annotate_text(html_content, annotations):
    """
    Takes HTML content and list of annotations, returns HTML with annotated spans
    """
    if not annotations:
        # Strip outer div tags but preserve inner HTML
        soup = BeautifulSoup(html_content, "html.parser")
        return mark_safe(soup.div.decode_contents() if soup.div else html_content)

    # Parse the HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Get the inner content without the outer div
    inner_html = soup.div.decode_contents() if soup.div else html_content

    # Sort annotations by start position
    sorted_annotations = sorted(
        annotations, 
        key=lambda x: x.from_pos.get('offset', 0) if isinstance(x.from_pos, dict) else (x.from_pos or 0)
    )

    result = []
    last_pos = 0

    for annotation in sorted_annotations:
        # Find the actual text we're looking for
        target_text = annotation.selected_text

        # Find where this text appears in the inner HTML
        text_start = inner_html.find(target_text, last_pos)
        if text_start != -1:
            # Add any content before the annotation
            if text_start > last_pos:
                result.append(inner_html[last_pos:text_start])

            # Add the annotated content
            text_end = text_start + len(target_text)
            annotated_content = inner_html[text_start:text_end]

            # Determine the appropriate class based on annotation type
            annotation_type = annotation.annotation_type.lower()
            css_class = (
                "textual-variant" if annotation_type == "variant" else "annotated-text"
            )

            result.append(
                f'<span class="{css_class}" '
                f'data-annotation-id="{annotation.id}" '
                f'data-annotation-type="{annotation_type}" '
                f'onclick="showAnnotation(event, this)">'
                f"{annotated_content}"
                f"</span>"
            )

            last_pos = text_end

    # Add any remaining content
    if last_pos < len(inner_html):
        result.append(inner_html[last_pos:])

    return mark_safe("".join(result))
