from django import forms
from wagtail.images.forms import ImageInsertionForm

from pages.image_formats import FORMAT_CHOICES, POSITIONS, SIZES, format_name


class ImageFormatForm(ImageInsertionForm):
    """
    The form shown after choosing an image to place in rich text, asking for
    its position, size and caption as separate choices instead of Wagtail's
    single list of formats. Wagtail's image chooser is set to use it in
    pages/apps.py.
    """

    format = None  # replaced by the three choices below
    position = forms.ChoiceField(
        choices=POSITIONS,
        initial="right",
        widget=forms.RadioSelect,
        help_text="Text below the image in the editor appears beside it on the page.",
    )
    size = forms.ChoiceField(
        choices=SIZES,
        initial="medium",
        widget=forms.RadioSelect,
        help_text="For left and right images. Full width images fill the width "
        "of the text.",
    )
    caption = forms.BooleanField(
        required=False,
        label="Show the alt text as a caption beneath the image",
    )

    field_order = ["position", "size", "caption", "image_is_decorative", "alt_text"]

    def __init__(self, *args, initial=None, **kwargs):
        initial = dict(initial or {})
        # when editing an image already in the text, start from its format
        if initial.get("format") in FORMAT_CHOICES:
            position, size, caption = FORMAT_CHOICES[initial["format"]]
            initial.update(position=position, size=size, caption=caption)
        super().__init__(*args, initial=initial, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("caption") and cleaned_data.get("image_is_decorative"):
            self.add_error(
                "caption",
                "A decorative image has no alt text to show as a caption",
            )
        if "position" in cleaned_data and "size" in cleaned_data:
            cleaned_data["format"] = format_name(
                cleaned_data["position"],
                cleaned_data["size"],
                cleaned_data.get("caption", False),
            )
        return cleaned_data
