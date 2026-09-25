from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect, render

from .forms import EntryForm
from .models import Entry


def index(request):
    """The guestbook: newest entries first, and a form to add one."""
    if request.method == "POST":
        form = EntryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thanks for signing.")
            # Redirect after a successful POST, so refreshing the page does not sign twice.
            return redirect("index")
    else:
        form = EntryForm()

    entries = Entry.objects.all()[:50]
    return render(request, "guestbook/index.html", {"form": form, "entries": entries})


def admin_login(request):
    """Django's own admin login, plus a hint while there is no account that can use it.

    A fresh deploy has no admin account, and the stock page gives no clue how to make one.
    """
    has_admin = get_user_model().objects.filter(is_superuser=True, is_active=True).exists()
    return admin.site.login(request, extra_context={"no_admin_yet": not has_admin})
