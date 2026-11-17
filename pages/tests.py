import tempfile

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from wagtail.images.formats import get_image_format, get_image_formats
from wagtail.images.models import Image
from wagtail.images.tests.utils import get_test_image_file
from wagtail.rich_text import expand_db_html

from pages.models import (
    CommonContentBlock,
    DividerBlock,
    ImageRowBlock,
    ImageTextBlock,
)
from pages.templatetags.table_of_contents import with_table_of_contents


class ImageFormatsTest(SimpleTestCase):
    def test_extra_formats_are_offered(self):
        names = [image_format.name for image_format in get_image_formats()]
        self.assertEqual(
            names,
            [
                "fullwidth",
                "left",
                "right",
                "left_small",
                "right_small",
                "left_caption",
                "right_caption",
                "fullwidth_caption",
            ],
        )

    def test_small_formats_fit_within_300px(self):
        for name, side in [("left_small", "left"), ("right_small", "right")]:
            image_format = get_image_format(name)
            self.assertEqual(image_format.filter_spec, "max-300x300")
            self.assertEqual(image_format.classname, f"richtext-image {side}")


class SmallImageFormatRenderingTest(TestCase):
    def test_right_small_renders_within_300px(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            # a 640 x 480 test image
            image = Image.objects.create(title="Ship", file=get_test_image_file())
            html = expand_db_html(
                f'<embed embedtype="image" id="{image.pk}" format="right_small" alt="Ship"/>'
            )

        self.assertIn('class="richtext-image right"', html)
        self.assertIn('width="300"', html)
        self.assertIn('height="225"', html)


class CaptionedImageFormatRenderingTest(TestCase):
    def test_right_caption_shows_alt_text_as_caption(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            # a 640 x 480 test image
            image = Image.objects.create(title="Ship", file=get_test_image_file())
            html = expand_db_html(
                f'<embed embedtype="image" id="{image.pk}" format="right_caption" '
                'alt="A ship &amp; its &lt;crew&gt;"/>'
            )

        self.assertIn(
            '<figure class="richtext-figure right" style="width: 500px">', html
        )
        self.assertIn('class="richtext-image"', html)
        self.assertIn(
            "<figcaption>A ship &amp; its &lt;crew&gt;</figcaption></figure>", html
        )


class TableOfContentsFilterTest(SimpleTestCase):
    def test_headings_get_unique_ids(self):
        html = with_table_of_contents(
            "<h2>Dati’s Language</h2><h3>Notes</h3><h3>Notes</h3>"
            '<h2 id="kept">Kept</h2><div class="block-heading">Books</div>'
        )
        self.assertIn('<h2 id="datis-language">', html)
        self.assertIn('<h3 id="notes">Notes</h3><h3 id="notes-2">Notes</h3>', html)
        self.assertIn('<h2 id="kept">', html)
        self.assertIn('<div class="block-heading" id="books">', html)

    def test_lists_headings_nested_by_level(self):
        html = with_table_of_contents(
            '<nav data-toc data-toc-depth="3"></nav>'
            "<h2>One</h2><h3>One A</h3><h4>Too deep</h4><h3>One B</h3><h2>Two</h2>"
        )
        self.assertIn(
            '<ul><li><a href="#one">One</a><ul>'
            '<li><a href="#one-a">One A</a></li>'
            '<li><a href="#one-b">One B</a></li></ul></li>'
            '<li><a href="#two">Two</a></li></ul>',
            html,
        )

    def test_numbered_uses_ordered_lists(self):
        html = with_table_of_contents(
            '<nav data-toc data-toc-depth="3" data-toc-numbered></nav>'
            "<h2>One</h2><h3>One A</h3>"
        )
        self.assertIn(
            '<ol><li><a href="#one">One</a><ol>'
            '<li><a href="#one-a">One A</a></li></ol></li></ol>',
            html,
        )

    def test_leaves_out_headings_in_accordions(self):
        html = with_table_of_contents(
            '<nav data-toc data-toc-depth="3"></nav><h2>Shown</h2>'
            "<details><summary>More</summary><h2>Hidden</h2></details>"
        )
        self.assertIn('href="#shown"', html)
        self.assertNotIn("Hidden</a>", html)


class LayoutBlockRenderingTest(TestCase):
    def setUp(self):
        media_root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=media_root))
        self.images = [
            Image.objects.create(title=f"Map {n}", file=get_test_image_file())
            for n in range(3)
        ]

    def render(self, block, data):
        return block.render(block.to_python(data))

    def test_image_text_wraps_text_around_the_image(self):
        html = self.render(
            ImageTextBlock(),
            {
                "image": self.images[0].pk,
                "caption": "Map of Sicily",
                "alt_text": "",
                "image_side": "right",
                "image_width": "half",
                "text": "<p>Book III follows the coast.</p>",
            },
        )
        self.assertIn('class="image-text image-text-right image-text-half"', html)
        self.assertIn('alt="Map 0"', html)
        self.assertIn("Map of Sicily</figcaption>", html)
        self.assertIn("<p>Book III follows the coast.</p>", html)

    def test_image_row_shows_up_to_four_columns(self):
        # list items as the CMS saves them, each with an id
        items = [
            {
                "type": "item",
                "id": str(n),
                "value": {"image": image.pk, "caption": image.title, "alt_text": ""},
            }
            for n, image in enumerate(self.images)
        ]
        html = self.render(ImageRowBlock(), {"images": items, "display": "row"})
        self.assertIn('style="--image-row-columns: 3"', html)
        self.assertEqual(html.count("<figure>"), 3)
        self.assertNotIn('src=""', html)
        self.assertIn("Map 2</figcaption>", html)

        html = self.render(ImageRowBlock(), {"images": items * 2, "display": "row"})
        self.assertIn('style="--image-row-columns: 4"', html)

    def test_image_row_as_carousel_shows_the_first_image(self):
        items = [
            {"image": image.pk, "caption": image.title, "alt_text": ""}
            for image in self.images
        ]
        html = self.render(ImageRowBlock(), {"images": items, "display": "carousel"})
        self.assertIn('x-data="{ current: 0, count: 3 }"', html)
        self.assertEqual(html.count('<figure class="is-hidden"'), 2)
        self.assertIn("of 3</span>", html)

    def test_divider_line_is_optional(self):
        self.assertNotIn("<hr>", self.render(DividerBlock(), {"show_line": False}))
        self.assertIn("<hr>", self.render(DividerBlock(), {"show_line": True}))


class BlockMenuTest(TestCase):
    """The groups, descriptions and previews in the CMS's "+" menu of blocks"""

    def render_previews(self):
        for name, block in CommonContentBlock().child_blocks.items():
            if not block.is_previewable:
                continue
            value = block.get_preview_value()
            with self.subTest(block=name):
                html = render_to_string(
                    block.get_preview_template(value),
                    {"bound_block": block.bind(value), "block_def": block},
                )
                self.assertIn('<article class="prose', html)

    def test_every_block_has_a_group_and_description(self):
        for name, block in CommonContentBlock().child_blocks.items():
            with self.subTest(block=name):
                self.assertTrue(block.meta.group)
                self.assertTrue(block.get_description())

    def test_previews_render_with_an_empty_media_library(self):
        self.render_previews()

    def test_previews_render_with_images(self):
        media_root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=media_root))
        for n in range(3):
            Image.objects.create(title=f"Map {n}", file=get_test_image_file())
        self.render_previews()

