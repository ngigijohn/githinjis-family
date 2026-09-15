from django import forms
from django.core.exceptions import ValidationError

from .models import (
    ContactMessage,
    Education,
    Employment,
    LifeEvent,
    ParentChild,
    Person,
    Place,
    Residence,
    Tag,
    Union,
)

CHECKBOX_CLASS = "mt-0.5 h-4 w-4 rounded border-line text-brand focus:ring-brand/30"
FILE_CLASS = (
    "block w-full text-sm text-muted file:mr-4 file:rounded-full file:border-0 file:bg-brand-soft "
    "file:px-4 file:py-2 file:text-sm file:font-semibold file:text-brand hover:file:bg-brand-soft/70"
)


class StyledFormMixin:
    """Apply the site's Tailwind classes to every widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.HiddenInput, forms.CheckboxSelectMultiple)):
                continue
            if isinstance(widget, forms.CheckboxInput):
                css = CHECKBOX_CLASS
            elif isinstance(widget, forms.ClearableFileInput):
                css = FILE_CLASS
            else:
                css = "input"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(**kwargs)


def place_field(label, **kwargs):
    """A text box for a place, suggesting known places (see the ``place_datalist`` tag)."""
    return forms.CharField(
        label=label,
        required=False,
        max_length=250,
        widget=forms.TextInput(attrs={"list": "place-options", "placeholder": "e.g. Othaya, Nyeri, Kenya", "autocomplete": "off"}),
        **kwargs,
    )


class PlaceFieldsMixin:
    """Take places as text ("Othaya, Nyeri") and store them as ``Place`` records on save."""

    place_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.place_fields:
            place = getattr(self.instance, name, None)
            if place is not None and name not in self.initial:
                self.initial[name] = place.full_name

    def save(self, commit=True):
        for name in self.place_fields:
            setattr(self.instance, name, Place.from_text(self.cleaned_data.get(name)))
        return super().save(commit)


class PersonForm(PlaceFieldsMixin, StyledFormMixin, forms.ModelForm):
    place_fields = ("birth_place", "death_place", "homeland")

    birth_place = place_field("Place of birth")
    death_place = place_field("Place of death")
    homeland = place_field("Ancestral home", help_text="Where their family's roots or land are (mũciĩ).")
    tag_names = forms.CharField(
        label="Tags",
        required=False,
        max_length=500,
        help_text="Separate with commas, e.g. Teacher, Church elder, Farmer.",
        widget=forms.TextInput(attrs={"list": "tag-options", "autocomplete": "off"}),
    )

    class Meta:
        model = Person
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "maiden_name",
            "nickname",
            "gender",
            "birth_date",
            "birth_date_approx",
            "is_living",
            "death_date",
            "birth_order",
            "named_after",
            "lineage",
            "photo",
            "biography",
            "needs_review",
        ]
        widgets = {
            "birth_date": DateInput(),
            "death_date": DateInput(),
            "biography": forms.Textarea(attrs={"rows": 6, "placeholder": "Stories, character, achievements, memories…"}),
        }
        labels = {"is_living": "This person is living"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_living"].widget.attrs["x-model"] = "living"
        named_after = self.fields["named_after"]
        named_after.queryset = Person.objects.order_by("first_name", "last_name")
        if self.instance.pk:
            named_after.queryset = named_after.queryset.exclude(pk=self.instance.pk)
            self.initial.setdefault("tag_names", ", ".join(tag.name for tag in self.instance.tags.all()))
        named_after.empty_label = "Not recorded"

    def save(self, commit=True):
        person = super().save(commit)
        tags = Tag.from_names(self.cleaned_data.get("tag_names"))
        if commit:
            person.tags.set(tags)
        else:
            save_m2m = self.save_m2m

            def save_m2m_with_tags():
                save_m2m()
                person.tags.set(tags)

            self.save_m2m = save_m2m_with_tags
        return person


class PersonCreateForm(PersonForm):
    """Add a person and, optionally, connect them to an existing relative in one step."""

    RELATION_CHOICES = [
        ("", "Not linked to anyone yet"),
        ("child", "Child of"),
        ("parent", "Parent of"),
        ("partner", "Partner / spouse of"),
    ]

    relation = forms.ChoiceField(choices=RELATION_CHOICES, required=False, label="Relationship")
    relationship_type = forms.ChoiceField(
        choices=ParentChild.Type.choices, required=False, initial=ParentChild.Type.BIOLOGICAL, label="Type"
    )
    union = forms.ModelChoiceField(
        queryset=Union.objects.none(), required=False, label="Other parent", empty_label="Unknown / not recorded"
    )
    union_type = forms.ChoiceField(
        choices=Union.Type.choices, required=False, initial=Union.Type.MARRIAGE, label="Union type"
    )

    def __init__(self, *args, relative=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.relative = relative
        self.fields["relation"].widget.attrs["x-model"] = "relation"
        if relative:
            self.fields["union"].queryset = relative.unions()
            self.fields["union"].label_from_instance = (
                lambda union: f"with {union.other(relative) or 'an unknown partner'}"
            )

    def clean(self):
        cleaned = super().clean()
        relation = cleaned.get("relation")
        if relation and not self.relative:
            self.add_error("relation", "Choose who this person is related to.")
        elif (
            relation == "parent"
            and (cleaned.get("relationship_type") or ParentChild.Type.BIOLOGICAL) == ParentChild.Type.BIOLOGICAL
            and self.relative.parent_links.filter(relationship_type=ParentChild.Type.BIOLOGICAL).count() >= 2
        ):
            self.add_error("relation", f"{self.relative} already has two biological parents recorded.")
        return cleaned

    def save_relationship(self, person):
        relation = self.cleaned_data.get("relation")
        relative = self.relative
        if not relation or not relative:
            return
        rtype = self.cleaned_data.get("relationship_type") or ParentChild.Type.BIOLOGICAL
        if relation == "child":
            union = self.cleaned_data.get("union")
            ParentChild.objects.create(parent=relative, child=person, relationship_type=rtype, union=union)
            other = union.other(relative) if union else None
            if other:
                ParentChild.objects.create(parent=other, child=person, relationship_type=rtype, union=union)
        elif relation == "parent":
            ParentChild.objects.create(parent=person, child=relative, relationship_type=rtype)
            ParentChild.attach_unions(relative)
        elif relation == "partner":
            Union.objects.create(
                partner_a=relative,
                partner_b=person,
                union_type=self.cleaned_data.get("union_type") or Union.Type.MARRIAGE,
            )


class LinkRelativeForm(StyledFormMixin, forms.Form):
    """Connect two people who are both already in the database."""

    RELATION_CHOICES = [
        ("parent", "Parent"),
        ("child", "Child"),
        ("partner", "Partner / spouse"),
    ]

    relation = forms.ChoiceField(choices=RELATION_CHOICES, label="Add as")
    relative = forms.ModelChoiceField(queryset=Person.objects.all(), widget=forms.HiddenInput)
    relationship_type = forms.ChoiceField(
        choices=ParentChild.Type.choices, required=False, initial=ParentChild.Type.BIOLOGICAL, label="Type"
    )
    union_type = forms.ChoiceField(
        choices=Union.Type.choices, required=False, initial=Union.Type.MARRIAGE, label="Union type"
    )

    def __init__(self, *args, person, **kwargs):
        super().__init__(*args, **kwargs)
        self.person = person
        self.link = None

    def clean(self):
        cleaned = super().clean()
        relative = cleaned.get("relative")
        relation = cleaned.get("relation")
        if not relative or not relation:
            if not relative:
                raise ValidationError("Pick a person from the search results.")
            return cleaned
        if relative.pk == self.person.pk:
            raise ValidationError("A person cannot be related to themselves.")
        rtype = cleaned.get("relationship_type") or ParentChild.Type.BIOLOGICAL
        if relation == "parent":
            link = ParentChild(parent=relative, child=self.person, relationship_type=rtype)
        elif relation == "child":
            link = ParentChild(parent=self.person, child=relative, relationship_type=rtype)
        else:
            link = Union(
                partner_a=self.person,
                partner_b=relative,
                union_type=cleaned.get("union_type") or Union.Type.MARRIAGE,
            )
        link.full_clean()  # raises ValidationError with a readable message
        self.link = link
        return cleaned

    def save(self):
        self.link.save()
        if isinstance(self.link, ParentChild):
            ParentChild.attach_unions(self.link.child)
        return self.link


class LifeEventForm(PlaceFieldsMixin, StyledFormMixin, forms.ModelForm):
    place_fields = ("place",)
    place = place_field("Place")
    field_order = ["event_type", "title", "date", "place", "description"]

    class Meta:
        model = LifeEvent
        fields = ["event_type", "title", "date", "description"]
        widgets = {
            "date": DateInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class ResidenceForm(PlaceFieldsMixin, StyledFormMixin, forms.ModelForm):
    place_fields = ("place",)
    place = place_field("Place", )
    field_order = ["place", "start_year", "end_year", "is_current", "notes"]

    class Meta:
        model = Residence
        fields = ["start_year", "end_year", "is_current", "notes"]

    def clean_place(self):
        if not self.cleaned_data.get("place", "").strip():
            raise ValidationError("Say where they lived.")
        return self.cleaned_data["place"]


class EducationForm(PlaceFieldsMixin, StyledFormMixin, forms.ModelForm):
    place_fields = ("place",)
    place = place_field("Place")
    field_order = ["institution", "level", "field_of_study", "place", "start_year", "end_year", "notes"]

    class Meta:
        model = Education
        fields = ["institution", "level", "field_of_study", "start_year", "end_year", "notes"]


class EmploymentForm(PlaceFieldsMixin, StyledFormMixin, forms.ModelForm):
    place_fields = ("place",)
    place = place_field("Place")
    field_order = ["employer", "role", "place", "start_year", "end_year", "is_current", "notes"]

    class Meta:
        model = Employment
        fields = ["employer", "role", "start_year", "end_year", "is_current", "notes"]


class ContactForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "message"]
        widgets = {
            "message": forms.Textarea(
                attrs={"rows": 5, "placeholder": "A correction, a missing relative, a story to share…"}
            )
        }
