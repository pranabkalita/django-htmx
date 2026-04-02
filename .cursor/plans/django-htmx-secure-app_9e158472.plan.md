---
name: django-htmx-secure-app
overview: Build a production-ready Django SSR + HTMX application from scratch using MySQL, TailwindCSS, Celery+Redis, FBV-only architecture, strong security controls, email verification, and TOTP 2FA.
todos:
  - id: bootstrap
    content: Scaffold Django project with domain-based app layout and dependency setup
    status: completed
  - id: config
    content: Implement split settings, MySQL, environment loader, and documented .env/.env.example
    status: completed
  - id: auth-models
    content: Build custom user, verification, 2FA, and security/audit models
    status: completed
  - id: auth-flows
    content: "Implement FBV auth flows: register/verify/login/forgot/reset/change/deactivate/logout"
    status: completed
  - id: htmx-ui
    content: Build reusable SSR+HTMX templates/layouts, partial rendering, push-url navigation, and progress bar
    status: completed
  - id: async-email
    content: Configure Celery+Redis and async email tasks with MAIL_DRIVER switching
    status: completed
  - id: security-rate-limit
    content: Apply CSRF/XSS-safe patterns, secure session settings, security middleware, and rate limiting
    status: completed
  - id: validation
    content: Add smoke tests and setup/run instructions for local and production-style execution
    status: completed
isProject: false
---

# Django HTMX Secure App Plan

## Proposed Project Structure

```text
/home/pranab/Pranab/PythonApps/django-htmx/
  manage.py
  requirements/
    base.txt
    dev.txt
    prod.txt
  config/
    __init__.py
    settings/
      __init__.py
      base.py
      dev.py
      prod.py
    urls.py
    wsgi.py
    asgi.py
    celery.py
  apps/
    common/
      apps.py
      middleware/
        request_id.py
        security_headers.py
      templatetags/
      views/
        public.py
      templates/
        layouts/
          guest.html
          auth.html
        partials/
          navbar_guest.html
          navbar_auth.html
          flash_messages.html
          htmx_progress.html
    accounts/
      apps.py
      domains/
        user/entities.py
        auth/value_objects.py
      services/
        auth_service.py
        email_service.py
        twofa_service.py
        password_service.py
      repositories/
        user_repo.py
        token_repo.py
      models/
        user.py
        email_verification.py
        twofa.py
        audit.py
      forms/
        auth_forms.py
        profile_forms.py
        twofa_forms.py
      views/
        auth_public.py
        auth_private.py
        profile.py
      tasks/
        email_tasks.py
      templates/
        accounts/
          login.html
          register.html
          forgot_password.html
          reset_password.html
          verify_email_notice.html
          dashboard.html
          account/
            profile.html
            change_password.html
            twofa.html
            deactivate.html
          partials/
            form_errors.html
            otp_qr_block.html
    pages/
      apps.py
      views/
        public.py
      templates/
        pages/
          landing.html
          about.html
          contact.html
  static_src/
    input.css
    js/
      app.js
      htmx_progress.js
  static/
    build/
  templates/
    base_shell.html
  logs/
    mail.log
  .env
  .env.example
  docker-compose.yml
  tailwind.config.js
  postcss.config.js
  package.json
```

## Architecture Decisions

- Use **FBV-only** handlers in `[apps/accounts/views](apps/accounts/views)` and `[apps/pages/views](apps/pages/views)`; no class-based views, no DRF.
- Keep business logic in `[apps/accounts/services](apps/accounts/services)` and persistence access in `[apps/accounts/repositories](apps/accounts/repositories)` to avoid fat views.
- Use domain folders (`domains/`) for explicit core concepts (user auth state, token lifecycles, 2FA state transitions).
- HTMX-first SSR pattern:
  - full page for regular requests
  - fragment/partial responses for `HX-Request`
  - `hx-push-url="true"` to preserve browser history.
- Centralize security defaults in `[config/settings/base.py](config/settings/base.py)` and custom middleware in `[apps/common/middleware](apps/common/middleware)`.

## Implementation Steps

1. **Bootstrap project and dependencies**
  - Initialize Django project in `[config](config)` and apps in `[apps](apps)`.
  - Install: Django, mysqlclient, celery, redis, django-ratelimit, pyotp, qrcode, python-dotenv/django-environ, django-htmx.
2. **Environment and settings design**
  - Create `[.env.example](.env.example)` with documented variables (DB, Redis, SMTP, `MAIL_DRIVER`, security flags, CSRF/session/cookie settings).
  - Add split settings: `[config/settings/base.py](config/settings/base.py)`, `[config/settings/dev.py](config/settings/dev.py)`, `[config/settings/prod.py](config/settings/prod.py)`.
  - Configure MySQL, static files, templates, logging, email backend switch by `MAIL_DRIVER`.
3. **Email driver abstraction**
  - In settings:
    - `MAIL_DRIVER=log` -> Django file email backend writing to `[logs/mail.log](logs/mail.log)`.
    - `MAIL_DRIVER=smtp` -> SMTP backend always active when selected, regardless of environment.
  - Add service wrapper in `[apps/accounts/services/email_service.py](apps/accounts/services/email_service.py)` and async task in `[apps/accounts/tasks/email_tasks.py](apps/accounts/tasks/email_tasks.py)`.
4. **Data model and auth core**
  - Custom user model in `[apps/accounts/models/user.py](apps/accounts/models/user.py)` using email as username; include `is_email_verified`, `is_active`.
  - Email verification token model + password reset workflow model strategy.
  - TOTP secret/recovery metadata model in `[apps/accounts/models/twofa.py](apps/accounts/models/twofa.py)`.
  - Audit/security event model for login, failed attempts, 2FA changes.
5. **Security hardening baseline**
  - Enforce CSRF middleware + secure cookie/session settings (`HttpOnly`, `Secure`, `SameSite`, rotation on login).
  - Add strict headers: X-Content-Type-Options, Referrer-Policy, frame protection, CSP starter policy.
  - Ensure XSS-safe templates (autoescape default + sanitized output conventions).
6. **Public pages + guest layout**
  - Implement landing/about/contact FBVs and templates.
  - Guest navbar behavior: 
    - not logged in -> Home, Login, Register, About, Contact
    - logged in -> Home, Dashboard, About, Contact
  - Build reusable partials in `[apps/common/templates/partials](apps/common/templates/partials)`.
7. **Auth flows (FBV only)**
  - Register -> create inactive-for-login account state (`is_email_verified=False`) -> send verification email via Celery.
  - Login -> block until email verified; then enforce 2FA challenge when enabled.
  - Forgot/reset password with expiring signed token links.
  - Change password -> invalidate session + force re-login.
  - Deactivate account -> confirmation + logout + state update.
8. **2FA implementation**
  - Enable flow: verify password, generate TOTP secret, show QR, confirm OTP.
  - Disable flow: password + OTP confirmation.
  - Login challenge step with short-lived pre-auth session marker.
9. **Rate limiting**
  - Apply endpoint-level limits on register/login/forgot/reset/verify/2FA actions using `django-ratelimit`.
  - Include IP + user/email dimension where appropriate.
  - Return user-friendly HTMX partial errors for throttled requests.
10. **HTMX SPA-like UX + progress bar**
  - Add global HTMX container and links/forms with push-url behavior.
    - Return partial templates for HTMX requests and full templates otherwise.
    - Add top progress bar script in `[static_src/js/htmx_progress.js](static_src/js/htmx_progress.js)` triggered by HTMX lifecycle events.
    - Implement graceful HTMX error surfaces (network/server validation).
11. **Authenticated layout and account sidebar card**
  - Full-width shell with mobile hamburger toggle.
    - Left sidebar nav + bottom-pinned account box (name, profile, logout) using flex column + `mt-auto` pattern in Tailwind.
12. **Queue and worker setup**
  - Configure Celery app in `[config/celery.py](config/celery.py)` with Redis broker/backend.
    - Add startup instructions for `celery worker` and `celery beat` (if needed for periodic jobs).
13. **Operational readiness**
  - Add logging, health-check endpoint, sane defaults for production security.
    - Provide migration and local run instructions.
    - Add smoke tests for critical auth and security paths.

## Core Config Files To Deliver

- `[config/settings/base.py](config/settings/base.py)`
- `[config/celery.py](config/celery.py)`
- `[config/urls.py](config/urls.py)`
- `[apps/accounts/models/user.py](apps/accounts/models/user.py)`
- `[apps/accounts/views/auth_public.py](apps/accounts/views/auth_public.py)`
- `[apps/accounts/views/auth_private.py](apps/accounts/views/auth_private.py)`
- `[apps/accounts/services/email_service.py](apps/accounts/services/email_service.py)`
- `[apps/accounts/tasks/email_tasks.py](apps/accounts/tasks/email_tasks.py)`
- `[apps/common/templates/layouts/guest.html](apps/common/templates/layouts/guest.html)`
- `[apps/common/templates/layouts/auth.html](apps/common/templates/layouts/auth.html)`
- `[static_src/js/htmx_progress.js](static_src/js/htmx_progress.js)`
- `[.env.example](.env.example)`

## .env / .env.example Variable Set (documented)

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `REDIS_URL`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `MAIL_DRIVER` (`log` or `smtp`)
- `MAIL_FROM_NAME`, `MAIL_FROM_EMAIL`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_USE_SSL`
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`

## Deliverables Mapping To Your Requested Output

- Clean scalable folder structure: covered in structure section.
- Key settings (DB, email, queue): covered in steps 2-3, 12.
- `.env` + `.env.example`: step 2 + variable set.
- Core models (User, email verification, 2FA): step 4.
- Middleware/security: step 5.
- Sample FBVs auth flow: step 7.
- HTMX integration + URL updates + progress bar: step 10.
- Tailwind setup: steps 1 and 11.
- Celery config: step 12.
- Security controls: steps 5, 7, 8, 9.
- Step-by-step setup instructions: step 13 plus runbook in README.

