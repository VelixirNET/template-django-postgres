"""The guestbook at /, Django's admin at /admin/. /healthz is answered in middleware."""

from django.contrib import admin
from django.urls import path

from guestbook import views

urlpatterns = [
    # Ahead of the admin's own routes: the stock login page, plus a first-run hint.
    path("admin/login/", views.admin_login),
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
]
