from datetime import timedelta
from django.contrib.auth import login
from django.conf import settings
from django.db import IntegrityError
from django.http import Http404
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms.auth_forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm
from apps.accounts.models import EmailVerificationToken, PasswordResetToken, User
from apps.accounts.services.auth_service import (
    authenticate_user,
    build_email_verification,
    build_password_reset,
    complete_password_reset,
    record_security_event,
    register_user,
)
from apps.accounts.services.job_service import enqueue_email_job
from apps.accounts.services.twofa_service import verify_otp
from apps.common import toasts
from apps.common.session_timeout import initialize_authenticated_session
from apps.common.views.rendering import htmx_redirect, render_htmx


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _normalize_link_token(token):
    token = (token or '').strip()
    # Raw MIME/QP logs can inject '=' soft-wrap markers when links are copied manually.
    return token.replace('=', '')


def _get_active_record_or_404(model, token):
    normalized_token = _normalize_link_token(token)
    record = model.objects.filter(token=normalized_token, used_at__isnull=True).first()
    if not record:
        raise Http404(f'No {model.__name__} matches the given query.')
    return record


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def register(request):
    if request.user.is_authenticated:
        return redirect(reverse('accounts:dashboard'))
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if User.objects.filter(email__iexact=form.cleaned_data['email']).exists():
            form.add_error('email', 'Email already registered.')
            return render_htmx(request, 'accounts/register.html', 'accounts/partials/register_content.html', {'form': form}, shell='guest')
        try:
            user = register_user(
                email=form.cleaned_data['email'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                password=form.cleaned_data['password'],
            )
            token = build_email_verification(user)
            verify_url = request.build_absolute_uri(reverse('accounts:verify_email', kwargs={'token': token.token}))
            site_url = request.build_absolute_uri('/').rstrip('/')
            app_name = settings.APP_NAME
            text_body = (
                f'Welcome to {app_name}, {user.first_name or user.email}.\n\n'
                f'Click the link below to verify your email and activate your account:\n\n'
                f'{verify_url}\n\n'
                f'This link expires in 24 hours.\n\n'
                f'If you did not create an account, you can safely ignore this email.\n\n'
                f'{app_name}\n{site_url}\nSupport: {settings.DEFAULT_FROM_EMAIL}'
            )
            enqueue_email_job(
                subject=f'Verify your account - {app_name}',
                body=text_body,
                recipients=[user.email],
                html_template='accounts/emails/verify_email.html',
                context={
                    'first_name': user.first_name or user.email,
                    'verify_url': verify_url,
                    'site_url': site_url,
                    'support_email': settings.DEFAULT_FROM_EMAIL,
                    'year': now().year,
                },
            )
            toasts.success(request, 'Registration complete. Verify your email before login.')
            return htmx_redirect(request, reverse('accounts:login'), shell='guest')
        except IntegrityError:
            form.add_error('email', 'Email already registered.')
    return render_htmx(request, 'accounts/register.html', 'accounts/partials/register_content.html', {'form': form}, shell='guest')


@ratelimit(key='post:email', rate='5/m', method='POST', block=True)
@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def login_view(request):
    if request.user.is_authenticated:
        return redirect(reverse('accounts:dashboard'))
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate_user(form.cleaned_data['email'], form.cleaned_data['password'])
        if not user:
            record_security_event(event_type='login_failed', ip_address=_client_ip(request))
            toasts.error(request, 'Invalid credentials.')
        elif not user.is_email_verified:
            record_security_event(event_type='login_blocked_unverified', user=user, ip_address=_client_ip(request))
            toasts.warning(request, 'Please verify your email before login.')
        elif hasattr(user, 'twofa_settings') and user.twofa_settings.is_enabled:
            request.session['pre_2fa_user_id'] = user.id
            request.session['pre_2fa_expires_at'] = int((timezone.now() + timedelta(minutes=5)).timestamp())
            request.session['pre_2fa_remember_me'] = bool(form.cleaned_data['remember_me'])
            toasts.info(request, 'Enter your authenticator code to continue.')
            return htmx_redirect(request, reverse('accounts:twofa_challenge'), shell='guest')
        else:
            login(request, user)
            request.session.cycle_key()
            record_security_event(event_type='login_success', user=user, ip_address=_client_ip(request))
            initialize_authenticated_session(request, browser_close=not form.cleaned_data['remember_me'])
            toasts.success(request, 'Welcome back.')
            return htmx_redirect(request, reverse('accounts:dashboard'), shell='auth')
    return render_htmx(request, 'accounts/login.html', 'accounts/partials/login_content.html', {'form': form}, shell='guest')


def verify_email(request, token):
    record = _get_active_record_or_404(EmailVerificationToken, token)
    if record.expires_at < timezone.now():
        toasts.error(request, 'Verification link expired. Request a new verification email.')
        return htmx_redirect(request, reverse('accounts:login'), shell='guest')
    record.user.is_email_verified = True
    record.user.save(update_fields=['is_email_verified'])
    record.used_at = timezone.now()
    record.save(update_fields=['used_at'])
    toasts.success(request, 'Email verified, you can login now.')
    return htmx_redirect(request, reverse('accounts:login'), shell='guest')


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def forgot_password(request):
    if request.user.is_authenticated:
        return redirect(reverse('accounts:dashboard'))
    form = ForgotPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = User.objects.filter(email__iexact=form.cleaned_data['email']).first()
        if user and user.is_email_verified:
            token = build_password_reset(user)
            reset_url = request.build_absolute_uri(reverse('accounts:reset_password', kwargs={'token': token.token}))
            site_url = request.build_absolute_uri('/').rstrip('/')
            app_name = settings.APP_NAME
            # Plain text body with URL on separate line with no preceding text to avoid wrapping issues
            reset_text_body = (
                f'Hi {user.first_name or user.email},\n\n'
                f'We received a request to reset your {app_name} password.\n\n'
                f'Click the link below to reset your password:\n\n'
                f'{reset_url}\n\n'
                f'This link expires in 1 hour.\n\n'
                f'If you did not request a password reset, you can safely ignore this email.\n\n'
                f'{app_name}\n{site_url}\nSupport: {settings.DEFAULT_FROM_EMAIL}'
            )
            enqueue_email_job(
                subject=f'Reset your password - {app_name}',
                body=reset_text_body,
                recipients=[user.email],
                html_template='accounts/emails/reset_password.html',
                context={
                    'first_name': user.first_name or user.email,
                    'reset_url': reset_url,
                    'site_url': site_url,
                    'support_email': settings.DEFAULT_FROM_EMAIL,
                    'year': now().year,
                },
            )
        elif user:
            token = build_email_verification(user)
            verify_url = request.build_absolute_uri(reverse('accounts:verify_email', kwargs={'token': token.token}))
            site_url = request.build_absolute_uri('/').rstrip('/')
            app_name = settings.APP_NAME
            text_body = (
                f'Hi {user.first_name or user.email},\n\n'
                f'Please verify your {app_name} account before resetting your password.\n\n'
                f'Click the link below to verify your email:\n\n'
                f'{verify_url}\n\n'
                f'This link expires in 24 hours.\n\n'
                f'{app_name}\n{site_url}\nSupport: {settings.DEFAULT_FROM_EMAIL}'
            )
            enqueue_email_job(
                subject=f'Verify your account - {app_name}',
                body=text_body,
                recipients=[user.email],
                html_template='accounts/emails/verify_email.html',
                context={
                    'first_name': user.first_name or user.email,
                    'verify_url': verify_url,
                    'site_url': site_url,
                    'support_email': settings.DEFAULT_FROM_EMAIL,
                    'year': now().year,
                },
            )
        toasts.info(request, 'If the email exists, a reset link has been sent.')
        return htmx_redirect(request, reverse('accounts:login'), shell='guest')
    return render_htmx(request, 'accounts/forgot_password.html', 'accounts/partials/forgot_password_content.html', {'form': form}, shell='guest')


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def resend_verification(request):
    if request.method != 'POST':
        return htmx_redirect(request, reverse('accounts:login'), shell='guest')

    email = (request.POST.get('email') or '').strip()
    user = User.objects.filter(email__iexact=email).first()
    if user and not user.is_email_verified:
        token = build_email_verification(user)
        verify_url = request.build_absolute_uri(reverse('accounts:verify_email', kwargs={'token': token.token}))
        site_url = request.build_absolute_uri('/').rstrip('/')
        app_name = settings.APP_NAME
        text_body = (
            f'Hi {user.first_name or user.email},\n\n'
            f'Click the link below to verify your {app_name} account:\n\n'
            f'{verify_url}\n\n'
            f'This link expires in 24 hours.\n\n'
            f'{app_name}\n{site_url}\nSupport: {settings.DEFAULT_FROM_EMAIL}'
        )
        enqueue_email_job(
            subject=f'Verify your account - {app_name}',
            body=text_body,
            recipients=[user.email],
            html_template='accounts/emails/verify_email.html',
            context={
                'first_name': user.first_name or user.email,
                'verify_url': verify_url,
                'site_url': site_url,
                'support_email': settings.DEFAULT_FROM_EMAIL,
                'year': now().year,
            },
        )

    toasts.info(request, 'If the account exists and is unverified, a verification email has been sent.')
    return htmx_redirect(request, reverse('accounts:login'), shell='guest')


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def reset_password(request, token):
    record = _get_active_record_or_404(PasswordResetToken, token)
    form = ResetPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if record.expires_at < timezone.now():
            toasts.error(request, 'Reset link expired. Request a new one.')
            return htmx_redirect(request, reverse('accounts:forgot_password'), shell='guest')
        complete_password_reset(record, form.cleaned_data['new_password'])
        record_security_event(event_type='password_reset_completed', user=record.user, ip_address=_client_ip(request))
        toasts.success(request, 'Password reset successful. Login again.')
        return htmx_redirect(request, reverse('accounts:login'), shell='guest')
    return render_htmx(request, 'accounts/reset_password.html', 'accounts/partials/reset_password_content.html', {'form': form}, shell='guest')


@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def twofa_challenge(request):
    if request.method == 'POST':
        expires_at = request.session.get('pre_2fa_expires_at', 0)
        if not expires_at or timezone.now().timestamp() > expires_at:
            request.session.pop('pre_2fa_user_id', None)
            request.session.pop('pre_2fa_expires_at', None)
            request.session.pop('pre_2fa_remember_me', None)
            toasts.error(request, '2FA session expired. Please login again.')
            return htmx_redirect(request, reverse('accounts:login'), shell='guest')

        user = User.objects.select_related('twofa_settings').filter(id=request.session.get('pre_2fa_user_id')).first()
        if not user:
            request.session.pop('pre_2fa_remember_me', None)
            return redirect('accounts:login')
        if not user.is_email_verified:
            request.session.pop('pre_2fa_user_id', None)
            request.session.pop('pre_2fa_expires_at', None)
            request.session.pop('pre_2fa_remember_me', None)
            record_security_event(event_type='login_blocked_unverified', user=user, ip_address=_client_ip(request))
            toasts.warning(request, 'Please verify your email before login.')
            return htmx_redirect(request, reverse('accounts:login'), shell='guest')
        if verify_otp(user.twofa_settings.secret, request.POST.get('otp_code', '')):
            login(request, user)
            request.session.cycle_key()
            remember_me = bool(request.session.pop('pre_2fa_remember_me', False))
            request.session.pop('pre_2fa_user_id', None)
            request.session.pop('pre_2fa_expires_at', None)
            initialize_authenticated_session(request, browser_close=not remember_me)
            record_security_event(event_type='login_success_2fa', user=user, ip_address=_client_ip(request))
            toasts.success(request, 'Login verified with 2FA.')
            return htmx_redirect(request, reverse('accounts:dashboard'), shell='auth')
        record_security_event(event_type='twofa_failed', user=user, ip_address=_client_ip(request))
        toasts.error(request, 'Invalid OTP code.')
    return render_htmx(request, 'accounts/twofa_challenge.html', 'accounts/partials/twofa_challenge_content.html', shell='guest')
