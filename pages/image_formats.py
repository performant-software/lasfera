# How images placed inside CMS rich text are laid out. Editors choose a
# position (left, right or full width), a size and whether to show a caption
# as separate choices (see pages/image_format_form.py); Wagtail stores the
# combination as a single format name on the image, so every combination is
# registered here as a format.
#
# Wagtail's own "fullwidth" format (800px wide) is the full width size. The
# floated sizes fit the image within a square, so a tall image beside a couple
# of paragraphs doesn't tower over them: 300 x 300 px for small, 500 x 500 px
# for medium (replacing Wagtail's own "left" and "right" formats, which are
# 500px wide at any height) and 700 x 700 px for large. The CSS is in
# static/css/custom.css.
from django.utils.html import escape, format_html
from wagtail.images.formats import (
    Format,
    register_image_format,
    unregister_image_format,
)
from wagtail.images.shortcuts import get_rendition_or_not_found

POSITIONS = [
    ("left", "Left, with text beside it"),
    ("right", "Right, with text beside it"),
    ("fullwidth", "Full width"),
]
SIZES = [("small", "Small"), ("medium", "Medium"), ("large", "Large")]
SIZE_FILTER_SPECS = {
    "small": "max-300x300",
    "medium": "max-500x500",
    "large": "max-700x700",
}
FULL_WIDTH_FILTER_SPEC = "width-800"


class CaptionedFormat(Format):
    """
    An image format that shows the image's alt text as a caption beneath it,
    since images in rich text have no caption field of their own. The image
    and caption go in a <figure> as wide as the image, with figure_classname
    setting its alignment.
    """

    def __init__(self, name, label, figure_classname, filter_spec):
        super().__init__(name, label, "richtext-image", filter_spec)
        self.figure_classname = figure_classname

    def image_to_html(self, image, alt_text, extra_attributes=None):
        rendition = get_rendition_or_not_found(image, self.filter_spec)
        attributes = {
            **(extra_attributes or {}),
            "alt": escape(alt_text),
            "class": self.classname,
        }
        return format_html(
            '<figure class="richtext-figure {}" style="width: {}px">'
            "{}<figcaption>{}</figcaption></figure>",
            self.figure_classname,
            rendition.width,
            rendition.img_tag(attributes),
            alt_text,
        )


def format_name(position, size, caption):
    """
    The format name for a combination of choices, matching the names already
    used in existing content: "left", "right_small", "fullwidth_caption"…
    """
    name = position
    if position != "fullwidth" and size != "medium":
        name += f"_{size}"
    if caption:
        name += "_caption"
    return name


# every format name, mapped to the choices it stands for
FORMAT_CHOICES = {}
for position, position_label in POSITIONS:
    sizes = [("medium", "")] if position == "fullwidth" else SIZES
    for size, size_label in sizes:
        for caption in (False, True):
            name = format_name(position, size, caption)
            FORMAT_CHOICES[name] = (position, size, caption)
            if name == "fullwidth":
                continue  # Wagtail's own format
            if name in ("left", "right"):
                unregister_image_format(name)  # Wagtail's, replaced below
            label = ", ".join(
                part
                for part in (
                    position_label.split(",")[0],
                    size_label.lower(),
                    "with caption" if caption else "",
                )
                if part
            )
            filter_spec = (
                FULL_WIDTH_FILTER_SPEC
                if position == "fullwidth"
                else SIZE_FILTER_SPECS[size]
            )
            if caption:
                register_image_format(
                    CaptionedFormat(name, label, position, filter_spec)
                )
            else:
                register_image_format(
                    Format(name, label, f"richtext-image {position}", filter_spec)
                )
