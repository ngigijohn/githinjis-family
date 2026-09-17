from django import forms

from genealogy.forms import CHECKBOX_CLASS, DateInput, PlaceFieldsMixin, StyledFormMixin, place_field
from genealogy.models import Person

from .models import Document, Photo, Recording


def people_field(label):
    return forms.ModelMultipleChoiceField(
        queryset=Person.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": CHECKBOX_CLASS}),
        label=label,
    )


class PhotoForm(StyledFormMixin, forms.ModelForm):
    people = people_field("Who is in this photo?")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].widget.attrs.update({"x-on:change": "preview($event)", "accept": "image/*"})

    class Meta:
        model = Photo
        fields = ["image", "caption", "date_taken", "description", "people"]
        widgets = {
            "date_taken": DateInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class RecordingForm(PlaceFieldsMixin, StyledFormMixin, forms.ModelForm):
    place_fields = ("place",)
    place = place_field("Where it was recorded")
    speakers = people_field("Who is speaking?")
    people = people_field("Who do they talk about?")
    field_order = ["title", "audio", "language", "recorded_on", "place", "description", "transcript", "speakers", "people"]

    class Meta:
        model = Recording
        fields = ["title", "audio", "language", "recorded_on", "description", "transcript", "speakers", "people"]
        widgets = {
            "recorded_on": DateInput(),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "What the recording is about, in a sentence or two."}),
            "transcript": forms.Textarea(attrs={"rows": 8, "placeholder": "Optional. A written version, or a translation."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["audio"].widget.attrs.update({"accept": "audio/*"})
        self.fields["language"].widget.attrs.update({"list": "language-options", "autocomplete": "off"})


class DocumentForm(PlaceFieldsMixin, StyledFormMixin, forms.ModelForm):
    place_fields = ("place",)
    place = place_field("Where it was issued or written")
    people = people_field("Who does it concern?")
    field_order = ["title", "document_type", "file", "date", "date_approx", "place", "description", "source", "privacy", "people"]

    class Meta:
        model = Document
        fields = ["title", "document_type", "file", "date", "date_approx", "description", "source", "privacy", "people"]
        widgets = {
            "date": DateInput(),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "What the document says, and anything it tells the family."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs.update({"accept": ".pdf,image/*,.txt,.doc,.docx"})
