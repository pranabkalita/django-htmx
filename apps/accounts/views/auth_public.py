from datetime import timedelta
from django.contrib.auth import login
from django.conf import settings
from django.db import IntegrityError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
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
from apps.accounts.services.twofa_service import verify_otp
from apps.accounts.tasks.email_tasks import send_email_task
from apps.common import toasts
from apps.common.session_timeout import initialize_authenticated_session
from apps.common.views.rendering import htmx_redirect, render_htmx


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def register(request):
    if request.user.is_authenticated:
        return redirect(reverse('accounts:dashboard'))
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
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
                f'Verify your email address to activate your account:\n{verify_url}\n\n'
                f'This link expires in 24 hours.\n\n'
                f'If you did not create an account, you can safely ignore this email.\n\n'
                f'{app_name}\n{site_url}\nSupport: {settings.DEFAULT_FROM_EMAIL}'
            )
            send_email_task.delay(
                f'Verify your account - {app_name}',
                text_body,
                [user.email],
                'accounts/emails/verify_email.html',
                {
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
    record = get_object_or_404(EmailVerificationToken, token=token, used_at__isnull=True)
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
        user = User.objects.filter(email=form.cleaned_data['email']).first()
        if user:
            token = build_password_reset(user)
            reset_url = request.build_absolute_uri(reverse('accounts:reset_password', kwargs={'token': token.token}))
            site_url = request.build_absolute_uri('/').rstrip('/')
            app_name = settings.APP_NAME
            reset_text_body = (
                f'Hi {user.first_name or user.email},\n\n'
                f'We received a request to reset your {app_name} password.\n\n'
                f'Reset your password using this link:\n{reset_url}\n\n'
                f'This link expires in 1 hour.\n\n'
                f'If you did not request a password reset, you can safely ignore this email.\n\n'
                f'{app_name}\n{site_url}\nSupport: {settings.DEFAULT_FROM_EMAIL}'
            )
            send_email_task.delay(
                f'Reset your password - {app_name}',
                reset_text_body,
                [user.email],
                'accounts/emails/reset_password.html',
                {
                    'first_name': user.first_name or user.email,
                    'reset_url': reset_url,
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
            f'Use this link to verify your {app_name} account:\n{verify_url}\n\n'
            f'This link expires in 24 hours.\n\n'
            f'{app_name}\n{site_url}\nSupport: {settings.DEFAULT_FROM_EMAIL}'
        )
        send_email_task.delay(
            f'Verify your account - {app_name}',
            text_body,
            [user.email],
            'accounts/emails/verify_email.html',
            {
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
    record = get_object_or_404(PasswordResetToken, token=token, used_at__isnull=True)
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
