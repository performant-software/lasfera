import tempfile

from django.test import SimpleTestCase, TestCase, override_settings
from wagtail.images.formats import get_image_format, get_image_formats
from wagtail.images.models import Image
from wagtail.images.tests.utils import get_test_image_file
from wagtail.rich_text import expand_db_html


class ImageFormatsTest(SimpleTestCase):
    def test_small_formats_are_offered(self):
        names = [image_format.name for image_format in get_image_formats()]
        self.assertEqual(
            names, ["fullwidth", "left", "right", "left_small", "right_small"]
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
