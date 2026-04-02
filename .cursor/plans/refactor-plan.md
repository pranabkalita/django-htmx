Read memory

Created memory file [](file:///home/pranab/.config/Code/User/workspaceStorage/a37ba3a4f1b17d6bf3535c2c515a4cb1/GitHub.copilot-chat/memory-tool/memories/ZjU3NGQxODgtNjZkZi00NDIwLWI2MWYtNzdhYTM0ODU2ZDFm/plan.md)

Here is the full structured remediation plan:

---

## Plan: Django HTMX App — Full Production Remediation

Fix all critical crashes, security vulnerabilities, broken features, dead architecture, and template duplication. Organized into 5 independently verifiable phases — Phase 1 must be completed before production, the rest eliminate technical debt.

---

## Phase 1: Crash & Critical Security Fixes
*All blocking. Do these before anything else.*

1. **Fix missing `redirect` import** — auth_public.py: add `from django.shortcuts import redirect`. Current code throws `NameError` on every 2FA login attempt with expired session.

2. **Rate-limit `twofa_challenge`** — auth_public.py: add `@ratelimit(key='ip', rate='10/m', method='POST', block=True)`. Currently zero throttle — TOTP codes are brute-forceable.

3. **Enforce password confirmation in `deactivate_account`** — auth_private.py: call `request.user.check_password(request.POST.get('password', ''))` and reject if wrong. Template shows a password field but the view ignores it entirely.

4. **Apply Django password validators in forms** — auth_forms.py: add `validate_password()` call in `clean()` for `RegisterForm` and `ResetPasswordForm`. Currently `AUTH_PASSWORD_VALIDATORS` is completely bypassed.

5. **Invalidate old tokens on re-issuance** — auth_service.py: in both `build_email_verification()` and `build_password_reset()`, call `.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())` before creating a new token. Multiple valid tokens can coexist today.

6. **Fix register race condition** — auth_public.py: remove `filter().exists()` check; wrap `create_user()` in `try/except IntegrityError` and call `form.add_error('email', ...)` on catch.

7. **Fix Celery hardcoded dev settings** — celery.py: change default from `config.settings.dev` to `config.settings.prod`; override via `DJANGO_SETTINGS_MODULE` environment variable in all environments.

8. **Remove `SECRET_KEY` insecure fallback** — base.py: remove `default='unsafe-dev-key'` so missing .env in production fails loudly.

---

## Phase 2: Security Hardening
*parallel with Phase 1 where independent*

9. **Fix CSP — remove `unsafe-inline`** — security_headers.py: remove `'unsafe-inline'` from `script-src`; move any remaining inline scripts to external files. Also remove `unpkg.com` from allowlist.

10. **Vendor HTMX / add SRI** — base_shell.html: move `htmx.min.js` to js or add `integrity="sha384-..."` SRI hash to the CDN `<script>` tag. No integrity check = supply chain attack surface.

11. **Add per-email rate limiting to login** — auth_public.py: stack `@ratelimit(key='post:email', rate='5/m', method='POST', block=True)` alongside the existing IP ratelimit on `login_view`.

12. **Add 2FA session expiry** — auth_public.py: when setting `pre_2fa_user_id`, also store `pre_2fa_expires = time.time() + 300`; reject in `twofa_challenge` if expired.

13. **Fix `MAIL_DRIVER` routing** — base.py: map `MAIL_DRIVER` env var to Django's `EMAIL_BACKEND` setting (`filebased` for `log`, `smtp` for `smtp`). dev.py: set `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'`. Remove the manual `MAIL_DRIVER` check in email_service.py.

14. **Encrypt TOTP secrets at rest** — add `django-fernet-fields` to base.txt; replace `CharField` for `secret` in twofa.py with encrypted field; add `FERNET_KEY` to .env.

---

## Phase 3: Architecture Cleanup

15. **Move business logic out of views into services** — *depends on Phase 1*
    - `register()` → `auth_service.register_user(form_data)`
    - `reset_password()` → `auth_service.complete_password_reset(record, new_password)`
    - `deactivate_account()` → `auth_service.deactivate_user(user)`
    - `profile()` → new `apps/accounts/services/user_service.py::update_profile(user, data)`

16. **Remove empty stub folders or implement them** — repositories and domains are 100% empty. Recommended: delete both. If keeping, implement at minimum: `user_repo.create()`, `user_repo.get_by_email()`, `token_repo.get_valid_verification_token()`.

17. **Wire up or delete `SecurityEvent`** — audit.py model is never written to. Either delete it (and its migration) or write to it from `auth_service` for: login_success, login_failure, password_reset, 2fa_enabled, 2fa_disabled, account_deactivated.

18. **Move `logout_view` to auth_private.py** — it has `@login_required` but lives in auth_public.py. Move to auth_private.py and update urls.py.

---

## Phase 4: Template & HTMX Fixes

19. **Extract duplicated account settings sidebar** — create `_settings_nav.html` and `_settings_header.html` partials; replace copy-pasted markup in all 4 account partials (profile_content.html, twofa_content.html, change_password_content.html, deactivate_content.html).

20. **Fix broken resend-verification feature** — login_content.html: the resend form POSTs `resend_email` to `forgot_password` which ignores it. Add a dedicated `resend_verification` view, URL, and fix the form action and field name.

21. **Fix double flash messages** — remove `{% include 'partials/flash_messages.html' %}` from inside auth content partials — the layout already includes it, causing duplication on full-page loads.

22. **Restyle 2FA challenge partial** — twofa_challenge_content.html is unstyled raw HTML. Apply the same Tailwind card pattern used in login/register.

23. **Fix hardcoded sidebar active state** — auth.html: replace `{% if request.path == '/account/dashboard/' %}` with `{% if request.resolver_match.view_name == 'accounts:dashboard' %}`.

24. **Fix dashboard hardcoded data** — dashboard_content.html: pass 2FA status from `dashboard()` view context; replace `"2FA Disabled"` hardcoded string with actual `user.twofa_settings.is_enabled` check.

25. **Fix navbar missing About & Contact links** — navbar_guest.html: add `pages:about` and `pages:contact` links per requirements.

---

## Phase 5: Performance & Reliability

26. **Add `select_related` to 2FA queries** — auth_public.py: `User.objects.select_related('twofa_settings').filter(id=...).first()` in `twofa_challenge`; chain `select_related` in login flow.

27. **Add Celery retry logic** — email_tasks.py: add `autoretry_for=(Exception,), max_retries=3, default_retry_delay=60` to `@shared_task`.

28. **Add `CONN_MAX_AGE` to DB settings** — base.py: add `'CONN_MAX_AGE': env.int('DB_CONN_MAX_AGE', default=60)` to the `DATABASES` dict.

29. **Add `__str__` methods to all models** — user.py, twofa.py, email_verification.py — missing `__str__` makes Django admin and debugging painful.

---

## Verification

1. `python manage.py test apps.accounts` — all existing tests pass
2. `python manage.py check --deploy` — zero critical warnings
3. Manual: register → verify email → login → dashboard renders
4. Manual: login with 2FA user — verify no `NameError` crash (Step 1 fix)
5. Manual: deactivate with wrong password → must return error (Step 3 fix)
6. Manual: register with password `"a"` → must fail with validation message (Step 4 fix)
7. Manual: request password reset twice → confirm first token is invalidated in DB (Step 5 fix)
8. Manual: navigate to About/Contact from navbar (Step 25 fix)
9. `grep -r "unsafe-inline" apps/` → zero results (Step 9 fix)
10. `grep -r "unpkg.com" templates/` → zero results (Step 10 fix)

---

## Key Decisions

- **Repositories (Step 16)**: Recommend deleting empty stubs outright. Empty folder facades pretending to be architecture are worse than nothing.
- **TOTP encryption (Step 14)**: Non-negotiable if the app is multi-tenant; if single-org internal tool it is still strongly recommended.
- **Dashboard widgets**: Finance data is clearly a UI demo — mark as placeholder, fix only the 2FA status widget with real data.