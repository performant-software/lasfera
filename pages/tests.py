import tempfile

from django.test import SimpleTestCase, TestCase, override_settings
from wagtail.images.formats import get_image_format, get_image_formats
from wagtail.images.models import Image
from wagtail.images.tests.utils import get_test_image_file
from wagtail.rich_text import expand_db_html

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
