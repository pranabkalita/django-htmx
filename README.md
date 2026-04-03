# Django HTMX Secure

A full-stack, production-ready web application built with Django, HTMX, Tailwind CSS, and MySQL. It delivers a fast, SPA-like user experience through server-side rendering and HTMX partial updates — without a JavaScript framework.

---

## Features

### Authentication
- User registration with email verification
- Login with rate-limiting and lockout protection
- Optional TOTP-based two-factor authentication (2FA)
- Forgot password and secure password reset
- Resend email verification
- Account deactivation (soft delete)

### Account Management
- Profile update
- Password change
- 2FA setup and teardown (with QR code provisioning)
- Active session listing with individual and bulk revoke

### Developer Experience
- HTMX-powered partial page rendering (no full-page reloads)
- Toast notification system (server-side messages → client-side toasts)
- Tailwind CSS with a watch mode for development
- Split settings: `dev.py`, `prod.py`, and `base.py`
- Celery task queue for async email delivery with automatic retries

### Security
- Custom `SecurityHeadersMiddleware` (CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy)
- HSTS, secure cookies, and SSL redirect enabled in production settings
- CSRF protection on all forms and HTMX requests
- Rate limiting on auth endpoints (`django-ratelimit`)
- Fernet encryption for TOTP secrets at rest
- Security event audit log (login, password changes, etc.)
- Request ID middleware for request tracing

---

## Tech Stack

| Layer         | Technology                              |
|---------------|-----------------------------------------|
| Backend       | Django 6.x (Python 3.12+)               |
| Frontend      | HTMX 1.9, Tailwind CSS 3.4              |
| Database      | MySQL 8.0 (SQLite for local dev)        |
| Task Queue    | Celery 5.x + Redis 7                    |
| Email (dev)   | File-based log backend                  |
| Email (prod)  | SMTP (any provider)                     |
| 2FA           | TOTP via `pyotp` + `qrcode`             |
| Encryption    | Fernet (`cryptography`)                 |
| Process Mgmt  | Gunicorn + systemd (production)         |

---

## Project Structure

```
.
├── apps/
│   ├── accounts/          # Auth, profile, 2FA, sessions
│   │   ├── domains/       # Value objects and entities
│   │   ├── forms/         # Django form classes
│   │   ├── migrations/    # Database migrations
│   │   ├── models/        # User, EmailToken, TwoFA, Audit
│   │   ├── repositories/  # Data access layer
│   │   ├── services/      # Business logic (auth, email, 2FA, sessions)
│   │   ├── tasks/         # Celery async tasks
│   │   ├── templates/     # Account HTML templates
│   │   └── views/         # auth_public.py, auth_private.py
│   ├── common/            # Shared infrastructure
│   │   ├── middleware/    # RequestID, SecurityHeaders
│   │   ├── templates/     # Layouts, partials (flash_messages, navbar)
│   │   ├── toasts.py      # Server-side toast message helper
│   │   └── views/         # render_htmx(), htmx_redirect() utilities
│   └── pages/             # Public marketing pages (landing, about, contact)
├── config/
│   ├── settings/
│   │   ├── base.py        # Shared settings (DB, email, Celery, security)
│   │   ├── dev.py         # Debug=True, console email backend
│   │   └── prod.py        # Debug=False, HTTPS, HSTS
│   ├── celery.py          # Celery app configuration
│   ├── urls.py            # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
├── static/
│   ├── build/output.css   # Compiled Tailwind CSS
│   └── js/                # HTMX progress bar, toasts.js
├── static_src/
│   └── input.css          # Tailwind CSS entry point
├── templates/
│   └── base_shell.html    # Root HTML shell
├── requirements/
│   ├── base.txt           # Core dependencies
│   ├── dev.txt            # Dev extras (includes base)
│   └── prod.txt           # Prod extras: gunicorn (includes base)
├── package.json           # Tailwind build scripts
├── tailwind.config.js
├── docker-compose.yml     # MySQL + Redis for local dev
└── manage.py
```

---

## Installation (Development)

### Prerequisites
- Python 3.12+
- Node.js 18+ and npm
- Docker and Docker Compose (for MySQL and Redis)
- Git

### 1. Clone the repository

```bash
git clone https://github.com/your-username/django-htmx.git
cd django-htmx
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install system build dependencies (Ubuntu/Debian)

Required to build `mysqlclient`:

```bash
sudo apt-get install -y pkg-config default-libmysqlclient-dev build-essential
```

### 4. Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements/dev.txt
```

### 5. Install Node dependencies and build CSS

```bash
npm install
npm run build
```

During development, use watch mode to auto-rebuild on template changes:

```bash
npm run watch
```

### 6. Start MySQL and Redis with Docker

```bash
docker-compose up -d
```

This starts:
- MySQL 8 on `localhost:3306` (database: `django_htmx`, root password: `secret`)
- Redis 7 on `localhost:6379`

### 7. Create the `.env` file

```bash
cp .env.example .env
```

Edit `.env` with your local values. See the [Environment Variables](#environment-variables) section below.

Minimum `.env` for development:

```env
DJANGO_SECRET_KEY=your-local-secret-key-here
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

DB_ENGINE=django.db.backends.mysql
DB_NAME=django_htmx
DB_USER=root
DB_PASSWORD=secret
DB_HOST=127.0.0.1
DB_PORT=3306

REDIS_URL=redis://127.0.0.1:6379/0

MAIL_DRIVER=log
MAIL_FROM_EMAIL=no-reply@localhost
```

### 8. Run database migrations

```bash
python manage.py migrate --settings=config.settings.dev
```

### 9. Create a superuser (optional)

```bash
python manage.py createsuperuser --settings=config.settings.dev
```

### 10. Start the development server

```bash
python manage.py runserver --settings=config.settings.dev
```

The app is now running at `http://127.0.0.1:8000`.

### 11. Start the Celery worker

Open a second terminal and run:

```bash
source .venv/bin/activate
celery -A config worker --loglevel=info
```

Without the Celery worker, operations that send email (registration, password reset) will queue tasks but not deliver them until the worker is running.

---

## Environment Variables

All environment variables are read from `.env` via `django-environ`.

### Application

| Variable                      | Default                     | Description                                                             |
|-------------------------------|-----------------------------|-------------------------------------------------------------------------|
| `DJANGO_SECRET_KEY`           | *(required)*                | Django secret key. Use a long random string.                            |
| `DJANGO_DEBUG`                | `false`                     | Enable debug mode. Never `true` in production.                          |
| `DJANGO_ALLOWED_HOSTS`        | `127.0.0.1,localhost`       | Comma-separated list of allowed hostnames.                              |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | *(empty)*                   | Required if behind a reverse proxy (e.g. `https://your-domain.com`).   |
| `FERNET_KEY`                  | *(derived from SECRET_KEY)* | Encryption key for TOTP secrets. Use a stable dedicated key in production. |

### Database

| Variable          | Default                             | Description                                |
|-------------------|-------------------------------------|--------------------------------------------|
| `DB_ENGINE`       | `django.db.backends.sqlite3`        | Use `django.db.backends.mysql` for MySQL.  |
| `DB_NAME`         | `django_htmx`                       | Database name.                             |
| `DB_USER`         | `root`                              | Database user.                             |
| `DB_PASSWORD`     | *(empty)*                           | Database password.                         |
| `DB_HOST`         | `127.0.0.1`                         | Database host.                             |
| `DB_PORT`         | `3306`                              | Database port.                             |
| `DB_CONN_MAX_AGE` | `60`                                | Persistent connection lifetime in seconds. |

### Redis / Celery

| Variable                | Default                       | Description                              |
|-------------------------|-------------------------------|------------------------------------------|
| `REDIS_URL`             | `redis://127.0.0.1:6379/0`    | Shorthand for broker and result backend. |
| `CELERY_BROKER_URL`     | *(falls back to `REDIS_URL`)* | Celery message broker URL.               |
| `CELERY_RESULT_BACKEND` | *(falls back to `REDIS_URL`)* | Celery task result storage URL.          |

### Email

| Variable          | Default                  | Description                                                                   |
|-------------------|--------------------------|-------------------------------------------------------------------------------|
| `MAIL_DRIVER`     | `log`                    | `log`: writes emails to files. `smtp`: sends real email via SMTP.             |
| `MAIL_FROM_EMAIL` | `no-reply@example.com`   | The `From` address for outbound email.                                        |
| `SMTP_HOST`       | `localhost`              | SMTP server hostname. Only used when `MAIL_DRIVER=smtp`.                      |
| `SMTP_PORT`       | `587`                    | SMTP server port.                                                             |
| `SMTP_USER`       | *(empty)*                | SMTP username.                                                                |
| `SMTP_PASSWORD`   | *(empty)*                | SMTP password.                                                                |
| `SMTP_USE_TLS`    | `true`                   | Enable STARTTLS (recommended for port 587).                                   |
| `SMTP_USE_SSL`    | `false`                  | Enable SSL/TLS directly (use for port 465; mutually exclusive with TLS).      |
| `MAIL_LOG_PATH`   | `logs/mail/`             | Directory for logged emails when `MAIL_DRIVER=log`.                           |

**Email driver behavior:**

- `MAIL_DRIVER=log` (default): Emails are written as files to `logs/mail/`. No SMTP configuration needed. Suitable for local development.
- `MAIL_DRIVER=smtp`: Real delivery via SMTP. Set all `SMTP_*` variables and run a Celery worker.
- In `dev.py`, the backend is overridden to `console` — emails print directly to the Django terminal, regardless of `MAIL_DRIVER`.

### Security

| Variable              | Default    | Description                                         |
|-----------------------|------------|-----------------------------------------------------|
| `SECURE_HSTS_SECONDS` | `31536000` | Set to `0` to disable HSTS in non-HTTPS setups.    |

---

## Running the App

### Common development commands

```bash
# Run server (dev settings)
python manage.py runserver --settings=config.settings.dev

# Apply migrations
python manage.py migrate --settings=config.settings.dev

# Open Django shell
python manage.py shell --settings=config.settings.dev

# Run tests
python manage.py test apps.accounts --settings=config.settings.dev

# Collect static files (production only)
python manage.py collectstatic --settings=config.settings.prod
```

### Celery worker

```bash
celery -A config worker --loglevel=info
```

### Tailwind CSS

```bash
npm run build    # One-time build (minified output)
npm run watch    # Rebuild automatically on file changes
```

> **Important:** Always run `npm run build` before deploying. Tailwind scans HTML templates and `static/js/*.js` to determine which utility classes to include. Missing a build step after changing either source will cause styles to be stripped.

---

## HTMX Usage Overview

This app uses HTMX for SPA-like navigation and form submissions without a client-side framework.

### How navigation works

Each page renders a persistent shell (navbar, sidebar) with a `#content` region that HTMX targets for partial swaps:

```html
<a hx-get="/account/profile/"
   hx-target="#content"
   hx-swap="innerHTML"
   hx-push-url="true">
  Profile
</a>
```

When a request arrives with the `HX-Request: true` header, `render_htmx()` in `apps/common/views/rendering.py` strips the layout and returns only the inner `#content` HTML. Full-page loads always receive the complete shell.

### Forms

Forms submit via HTMX with the same pattern:

```html
<form hx-post="{% url 'accounts:profile' %}"
      hx-target="#content"
      hx-swap="innerHTML"
      hx-push-url="true">
```

### Toast notifications

Views emit typed toast messages using the shared helper:

```python
from apps.common.toasts import toasts

toasts.success(request, "Profile updated successfully.")
toasts.error(request, "Invalid credentials.")
```

Toast data travels via Django's Messages framework, is serialised into `data-*` attributes by `flash_messages.html`, and is hydrated into animated toast cards by `static/js/toasts.js` on every page load and after every HTMX swap.

---

## Security Features

| Feature                     | Implementation                                    |
|-----------------------------|---------------------------------------------------|
| CSRF protection             | Django middleware + HTMX `hx-headers` integration |
| Security response headers   | `SecurityHeadersMiddleware` (CSP, X-Frame, etc.)  |
| Rate limiting               | `django-ratelimit` on login and auth endpoints    |
| Password hashing            | Django's default PBKDF2 with SHA-256              |
| TOTP secret encryption      | Fernet symmetric encryption at rest               |
| Secure cookies              | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`     |
| HSTS                        | Enabled in `prod.py` with preload and subdomains  |
| SSL redirect                | `SECURE_SSL_REDIRECT=True` in `prod.py`           |
| Audit logging               | `SecurityEvent` model tracks auth events          |
| Request tracing             | `RequestIDMiddleware` injects `X-Request-ID`      |

---

## Troubleshooting

**Migrations fail with a MySQL connection error**
Ensure Docker is running and the MySQL container is ready:
```bash
docker-compose up -d && docker-compose ps
```
Wait a few seconds after first start for MySQL to finish initialising.

**Emails are not appearing anywhere**
In development, check the `logs/mail/` directory (or the terminal if using `dev.py`). If using `MAIL_DRIVER=smtp`, confirm your SMTP credentials and that the Celery worker is running.

**Toast notifications do not appear after HTMX swaps**
Tailwind purges CSS classes it does not detect at build time. After modifying `toasts.js` or adding new toast styles, rebuild the CSS:
```bash
npm run build
```

**Tailwind styles are missing or incorrect**
Run `npm run build` to regenerate `static/build/output.css`. During development, `npm run watch` keeps it updated automatically.

**Celery worker is not processing tasks**
Verify Redis is reachable:
```bash
docker-compose ps
redis-cli ping   # Expected: PONG
```
Check the worker terminal for connection errors and ensure `CELERY_BROKER_URL` in `.env` points to a running Redis instance.

**Static files return 404 in production**
Run `python manage.py collectstatic --settings=config.settings.prod` and confirm your Nginx `location /static/` block points to `STATIC_ROOT`.
8. Run celery worker: `celery -A config worker -l info`

## Notes
- `MAIL_DRIVER=log` stores generated emails in `logs/mail/`.
- `MAIL_DRIVER=smtp` sends via SMTP regardless of environment.
- Login is blocked until email is verified.
