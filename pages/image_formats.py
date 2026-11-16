# Extra image sizes for images in CMS rich text, alongside Wagtail's built-in
# "Full width" (800px wide) and "Left-aligned"/"Right-aligned" (500px wide).
# The small formats fit the image within 300 x 300 px, so a tall image floated
# beside a couple of paragraphs doesn't tower over them. They use the same CSS
# classes as the built-in formats (see static/css/custom.css).
from django.utils.html import escape, format_html
from wagtail.images.formats import Format, register_image_format
from wagtail.images.shortcuts import get_rendition_or_not_found

register_image_format(
    Format("left_small", "Left-aligned (small)", "richtext-image left", "max-300x300")
)
register_image_format(
    Format(
        "right_small", "Right-aligned (small)", "richtext-image right", "max-300x300"
    )
)


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


register_image_format(
    CaptionedFormat("left_caption", "Left-aligned with caption", "left", "width-500")
)
register_image_format(
    CaptionedFormat(
        "right_caption", "Right-aligned with caption", "right", "width-500"
    )
)
register_image_format(
    CaptionedFormat(
        "fullwidth_caption", "Full width with caption", "fullwidth", "width-800"
    )
)
