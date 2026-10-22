from django import forms
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.shortcuts import redirect, render

from .models import log_change


class SetupForm(forms.Form):
    username = forms.CharField(max_length=40, initial="gaggies", help_text="What you type to log in")
    first_name = forms.CharField(max_length=60, initial="Gaggies", label="Your name")
    password = forms.CharField(widget=forms.PasswordInput, help_text="At least 8 characters. Not your bank PIN!")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Type the password again")

    def clean(self):
        cd = super().clean()
        if cd.get("password") != cd.get("password2"):
            raise forms.ValidationError("The two passwords are not the same.")
        if cd.get("password"):
            try:
                validate_password(cd["password"])
            except forms.ValidationError as e:
                self.add_error("password", e)
        return cd


def setup(request):
    """First start only: create the owner's login."""
    if User.objects.exists():
        return redirect("login")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        u = User.objects.create_superuser(form.cleaned_data["username"].strip(), password=form.cleaned_data["password"],
                                          first_name=form.cleaned_data["first_name"].strip())
        login(request, u)
        log_change(u, "Users", u.username, "owner login created")
        return redirect("core:dashboard")
    return render(request, "core/setup.html", {"form": form})
