"""
Three small middlewares that keep the app honest about its database.

    HealthCheckMiddleware           /healthz, answered before anything else runs
    SetupModeMiddleware             no database bound yet: every page is the setup page
    DatabaseUnavailableMiddleware   the database dropped out mid-request: a 503 that says so

Their order in settings.MIDDLEWARE matters, and the comments there say why.
"""

import logging

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.db import Error, InterfaceError, OperationalError, connection
from django.http import HttpResponse
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def plain(text, status=200):
    return HttpResponse(text, status=status, content_type="text/plain; charset=utf-8")


class HealthCheckMiddleware:
    """Liveness and readiness in one: this app is useless without its database, so a failed
    query takes it out of rotation rather than letting it serve errors.

    It runs first, before anything reads the Host header. The platform's probe addresses the
    container by IP, and Django would reject that as a disallowed host long before any view
    got to answer.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != "/healthz":
            return self.get_response(request)
        if settings.SETUP_MODE:
            return plain("ok (setup mode: no database bound)")
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Error as exc:
            logger.error("health check failed: %s", exc)
            return plain("database unreachable", status=503)
        return plain("ok")


class SetupModeMiddleware:
    """No database bound yet. Rather than failing on every page (sessions, the admin and the
    guestbook all need one), answer every page with the steps that fix it. The status is 200:
    the app is doing exactly what it should, and the page stays reachable.
    """

    def __init__(self, get_response):
        if not settings.SETUP_MODE:
            # A database is bound. Take this middleware out of the chain entirely.
            raise MiddlewareNotUsed
        self.get_response = get_response

    def __call__(self, request):
        return HttpResponse(render_to_string("guestbook/setup.html"))


class DatabaseUnavailableMiddleware:
    """The database went away after start-up: a failover, a restart, a rotated password.
    Explain the wait with a 503 instead of Django's bare 500. Requests succeed again on their
    own once it is back, because every request opens (or health-checks) its connection.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not isinstance(exception, (OperationalError, InterfaceError)):
            return None
        logger.error("database unreachable: %s", exception)
        page = render_to_string("guestbook/waiting.html", {"error": exception})
        return HttpResponse(page, status=503)
