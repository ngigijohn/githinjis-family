from django import forms

from genealogy.forms import CHECKBOX_CLASS, DateInput, StyledFormMixin
from genealogy.models import Person

from .models import Photo


class PhotoForm(StyledFormMixin, forms.ModelForm):
    people = forms.ModelMultipleChoiceField(
        queryset=Person.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": CHECKBOX_CLASS}),
        label="Who is in this photo?",
    )

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
