# Extra image sizes for images in CMS rich text, alongside Wagtail's built-in
# "Full width" (800px wide) and "Left-aligned"/"Right-aligned" (500px wide).
# The small formats fit the image within 300 x 300 px, so a tall image floated
# beside a couple of paragraphs doesn't tower over them. They use the same CSS
# classes as the built-in formats (see static/css/custom.css).
from wagtail.images.formats import Format, register_image_format

register_image_format(
    Format("left_small", "Left-aligned (small)", "richtext-image left", "max-300x300")
)
register_image_format(
    Format(
        "right_small", "Right-aligned (small)", "richtext-image right", "max-300x300"
    )
)
