from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render

from genealogy.models import ContactMessage

from .forms import LoginForm, SignupForm


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


def signup(request):
    if request.user.is_authenticated:
        return redirect("genealogy:home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        note = form.cleaned_data.get("relationship_note")
        ContactMessage.objects.create(
            name=user.get_full_name() or user.username,
            email=user.email,
            message=f"New account request from “{user.username}”. Relationship: {note or 'not given'}",
        )
        return redirect("accounts:pending")
    return render(request, "accounts/signup.html", {"form": form})


def pending(request):
    return render(request, "accounts/pending.html")
