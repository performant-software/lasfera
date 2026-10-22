from django.test import TestCase, override_settings
from django.urls import reverse

BANNER = "Anything you add or change here may be removed"


class TestSiteBannerTest(TestCase):
    def test_hidden_by_default(self):
        self.assertNotContains(self.client.get(reverse("dmca")), BANNER)
        self.assertNotContains(self.client.get(reverse("admin:login")), BANNER)

    @override_settings(TEST_SITE_BANNER=True)
    def test_shown_on_site_and_admin(self):
        self.assertContains(self.client.get(reverse("dmca")), BANNER)
        self.assertContains(self.client.get(reverse("admin:login")), BANNER)
