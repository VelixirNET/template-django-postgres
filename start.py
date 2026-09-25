"""
Start the guestbook: bring the schema up to date, create the first admin if asked to, then
hand the process over to gunicorn.

The Procfile runs this as `python start.py` rather than ./start.py: executable bits do not
survive a checkout on Windows, and the interpreter does not need them.

Migrations run here, on every start, because the build has no database to run them against.
When the database cannot be reached yet (a failover, a rotated password waiting for a
redeploy, a database still starting), this keeps retrying rather than exiting, and the port
answers with a page that explains the wait. A crash loop would read as "the platform is
broken", and this way the app recovers by itself the moment the database is back.
"""

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

PORT = int(os.environ.get("PORT", "8080"))
RETRY_SECONDS = 5

# Any number works, as long as nothing else in the database takes the same advisory lock.
MIGRATION_LOCK = 7_214_202_611


def say(message):
    print(message, flush=True)


def run_gunicorn():
    """Replace this process with gunicorn, so it receives the platform's stop signal itself.

    Its settings are in gunicorn.conf.py, which it reads on its own.
    """
    sys.stdout.flush()
    os.execvp(sys.executable, [sys.executable, "-m", "gunicorn", "config.wsgi"])


class WaitingPage(BaseHTTPRequestHandler):
    """What the port answers while the database is out of reach: a 503 that says why."""

    last_error = None

    def do_GET(self):
        if self.path.split("?")[0] == "/healthz":
            body, kind = b"waiting for the database", "text/plain"
        else:
            from django.template.loader import render_to_string

            body = render_to_string("guestbook/waiting.html", {"error": self.last_error}).encode()
            kind = "text/html"
        self.send_response(503)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Retry-After", str(RETRY_SECONDS))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *args):
        pass  # The retry messages are the useful part of the log.


def open_waiting_page():
    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), WaitingPage)
    except OSError as exc:
        say(f"could not open port {PORT} for the waiting page: {exc}")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def migrate():
    """Apply any new migrations, then create the admin, both under one lock."""
    from django.core.management import call_command
    from django.db import connection

    # Several replicas starting at once would race the same migrations. The advisory lock
    # makes them take turns: the first applies them, the others find nothing left to do.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [MIGRATION_LOCK])
    try:
        call_command("migrate", interactive=False)
        create_admin()
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [MIGRATION_LOCK])


def create_admin():
    """Create the admin named in DJANGO_SUPERUSER_USERNAME, once.

    An existing account is left alone, password included: it may have been changed in the
    admin since, and resetting it on every deploy would quietly undo that.
    """
    username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
    if not username and not password:
        return
    if not (username and password):
        say("Set both DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD to create an admin.")
        return

    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(
                username=username,
                email=os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip(),
                password=password,
            )
            say(f"created admin account {username!r}")
    except Exception as exc:
        # The guestbook works without an admin, so this never holds up the start.
        say(f"could not create admin account {username!r}: {exc}")


def main():
    if not os.environ.get("DATABASE_URL", "").strip():
        say(
            "DATABASE_URL is not set, so this app is serving its setup page.\n"
            "On velixir: create a managed Postgres, bind it to this app as DATABASE_URL, then redeploy.\n"
            "Locally: DATABASE_URL=postgres://user:pass@localhost:5432/guestbook python start.py"
        )
        run_gunicorn()

    import django

    django.setup()
    from django.db import connections

    # Answer on the port from the first second, even while the database keeps us waiting.
    waiting_page = open_waiting_page()

    attempt = 0
    while True:
        attempt += 1
        try:
            migrate()
            break
        except Exception as exc:
            WaitingPage.last_error = str(exc).strip()
            if attempt == 1 or attempt % 12 == 0:
                say(f"database not ready yet (attempt {attempt}): {WaitingPage.last_error}")
            connections.close_all()
            time.sleep(RETRY_SECONDS)

    say("database ready")
    if waiting_page:
        waiting_page.shutdown()
        waiting_page.server_close()
    run_gunicorn()


if __name__ == "__main__":
    main()
