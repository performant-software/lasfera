from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pages"

    def ready(self):
        # Ask for the position, size and caption of an image placed in rich
        # text as separate choices
        from wagtail.images.views import chooser

        from pages.image_format_form import ImageFormatForm

        chooser.ImageInsertionForm = ImageFormatForm
