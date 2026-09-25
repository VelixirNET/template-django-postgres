# Django + Postgres

[![Deploy on velixir](https://velixir.net/img/deploy-on-velixir.svg)](https://velixir.net/new?template=django-postgres)

A real Django project, live on its own URL in minutes: a guestbook with a model, a form and
the Django admin, served by gunicorn and backed by managed Postgres. Django 5.2 (the current
LTS) on Python 3.13.

[Deploy it on velixir](https://velixir.net/new?template=django-postgres).

The guestbook is there so there is something to click. What is worth keeping is the setup
around it: settings from the environment, static files built into the image, migrations that
wait for the database, and a secret key you never have to think about. Replace the guestbook
with your own app and keep the rest.

## What it shows

- **Settings from the environment.** One `settings.py` for your laptop and for velixir.
  `DATABASE_URL` becomes `DATABASES` through dj-database-url, and TLS needs no code: psycopg
  hands `sslmode=require` to libpq, which encrypts without checking the certificate against
  public CAs, exactly what velixir's own CA calls for.
- **A secret key that looks after itself.** Set `DJANGO_SECRET_KEY` if you like. Without it,
  the key is derived from `DATABASE_URL`, so it is the same in every process and survives
  restarts. A fresh random key on each boot would sign everyone out whenever the app
  restarted or woke from sleep, and two processes would disagree about every session.
- **Static files at build time.** `collectstatic` runs during the build (see
  `nixpacks.toml`), and WhiteNoise serves the result from the image with long cache headers,
  the admin's CSS included. No bucket, no CDN, and no work at start.
- **Migrations on start, without the crash loop.** `start.py` runs `migrate` before gunicorn
  takes over. While the database is unreachable it retries every few seconds, and the port
  answers with a page explaining the wait instead of the app exiting. A Postgres advisory lock
  stops several replicas racing the same migration.
- **A setup page instead of a crash.** Start it with no database and every page says exactly
  how to bind one, while `/healthz` stays green.
- **Correct behind the proxy.** HTTPS is the edge's job, so the app never redirects to it
  (that can loop). CSRF trusts `https://*.velixir.run` explicitly, so forms work whichever
  scheme the forwarded header reports.
- **An honest health check.** `/healthz` runs `SELECT 1`, and it answers the platform's probe
  even though that addresses the container by IP rather than by an allowed hostname.

## Setting it up on velixir

Deploy it from the gallery. velixir creates a managed Postgres, binds it to the app as
`DATABASE_URL`, and holds the first deploy until the database is running, so the app starts
connected. Migrations run on first boot.

To sign in to the admin at `/admin/`, set `DJANGO_SUPERUSER_USERNAME` and
`DJANGO_SUPERUSER_PASSWORD` (and, if you like, `DJANGO_SUPERUSER_EMAIL`) on the app's
Environment tab, then redeploy. The account is created on the next start. The variables never
touch an account that already exists, so change its password in the admin from then on.

By hand, for example after deploying your own copy with `velixir deploy`:

1. Create a managed Postgres from the Databases page, or run `velixir db create`.
2. Bind it to the app as `DATABASE_URL`: on the database's page under Bound apps, or
   `velixir db bind <database-id> --app <app-id>`.
3. Redeploy, with the Redeploy button on the live release in the Deploys tab.

**On your own domain,** add it to `DJANGO_ALLOWED_HOSTS`, comma-separated
(`example.com,www.example.com`, or `.example.com` for every subdomain). The same names are
trusted for CSRF over HTTPS, so nothing else needs changing.

## Configuration

| Variable | Default | Does |
| --- | --- | --- |
| `DATABASE_URL` | set by velixir | The Postgres to use. Without it, the app serves its setup page. |
| `DJANGO_SECRET_KEY` | derived from `DATABASE_URL` | Signs sessions and reset links. Set it to keep sessions through a database password change. |
| `DJANGO_ALLOWED_HOSTS` | none | Custom domains, comma-separated. Any `*.velixir.run` name is always allowed. |
| `DJANGO_SUPERUSER_USERNAME`, `_PASSWORD`, `_EMAIL` | none | Creates this admin account on start, if it does not exist yet. |
| `DJANGO_DEBUG` | off | `1` turns on Django's debug pages. Never on a public URL. |
| `WEB_CONCURRENCY` | `2` | gunicorn worker processes, four threads each. |
| `GUNICORN_CMD_ARGS` | none | Any other gunicorn flag, for example `--access-logfile -`. |

## Running it locally

```bash
python -m venv .venv
. .venv/bin/activate                 # .venv\Scripts\activate on Windows
pip install -r requirements.txt
export DATABASE_URL=postgres://user:pass@localhost:5432/guestbook DJANGO_DEBUG=1
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8080
```

Then open http://localhost:8080. With no `sslmode` in the URL, the connection is plain TCP,
which is what a local Postgres expects. `DJANGO_DEBUG=1` serves static files straight from the
app folders, so there is no need to run `collectstatic` first.

## Deploying

```bash
velixir deploy
```

## Things to know before you rely on it

**Uploads need a bucket.** The container's disk is wiped on every deploy, so a `FileField` or
`ImageField` saving to local storage loses its files. Point Django's default storage at
S3-compatible object storage (django-storages) first.

**Email goes over HTTPS.** Outbound SMTP is blocked, so Django's SMTP backend cannot send.
The template prints mail to the log instead. For real mail, use an email API such as
Postmark, Resend or Brevo through django-anymail.

**The guestbook is a public form.** Anyone can sign it, and there is no spam protection.
Moderate from the admin, and add a captcha or a login before leaving it somewhere people will
find it.

**Changing the database password signs everyone out,** unless `DJANGO_SECRET_KEY` is set,
because the derived key changes with it.

**Migrations run on every start.** Fine for this app and most others. While a deploy rolls
out, old and new code briefly share the database, so keep each migration compatible with the
code before it: add a column in one deploy, start relying on it in the next.

**The certificate is not verified.** The connection is encrypted, but `sslmode=require` does
not check who issued the certificate, which matches what it means everywhere else. The traffic
never leaves velixir's private network, and the platform CA is not published, so there is
nothing to pin yet.

**The Free plan sleeps.** After 15 idle minutes the app stops, and the next visit wakes it.
That first request takes a few seconds while Django starts and checks its migrations.

## Licence

MIT.
