from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from genealogy.forms import StyledFormMixin


class LoginForm(StyledFormMixin, AuthenticationForm):
    pass


class SignupForm(StyledFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    relationship_note = forms.CharField(
        label="How are you related to the family?",
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Grandson of John Ngigi through George Githinji"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["first_name", "last_name", "username", "email"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False  # an administrator approves new accounts
        if commit:
            user.save()
        return user
