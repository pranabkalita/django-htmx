from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from apps.accounts.forms.auth_forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm
from apps.accounts.models import EmailVerificationToken, PasswordResetToken, User
from apps.accounts.services.auth_service import authenticate_user, build_email_verification, build_password_reset
from apps.accounts.services.twofa_service import verify_otp
from apps.accounts.tasks.email_tasks import send_email_task
from apps.common.views.rendering import htmx_redirect, render_htmx


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if User.objects.filter(email=form.cleaned_data['email']).exists():
            form.add_error('email', 'Email already registered.')
        else:
            user = User.objects.create_user(
                email=form.cleaned_data['email'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                password=form.cleaned_data['password'],
            )
            token = build_email_verification(user)
            verify_url = request.build_absolute_uri(reverse('accounts:verify_email', kwargs={'token': token.token}))
            send_email_task.delay('Verify your email', f'Verify here: {verify_url}', [user.email])
            messages.success(request, 'Registration complete. Verify your email before login.')
            return htmx_redirect(request, reverse('accounts:login'))
    return render_htmx(request, 'accounts/register.html', 'accounts/partials/register_content.html', {'form': form})


@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def login_view(request):
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate_user(form.cleaned_data['email'], form.cleaned_data['password'])
        if not user:
            messages.error(request, 'Invalid credentials.')
        elif not user.is_email_verified:
            messages.error(request, 'Please verify your email before login.')
        elif hasattr(user, 'twofa_settings') and user.twofa_settings.is_enabled:
            request.session['pre_2fa_user_id'] = user.id
            return htmx_redirect(request, reverse('accounts:twofa_challenge'))
        else:
            login(request, user)
            request.session.cycle_key()
            if not form.cleaned_data['remember_me']:
                request.session.set_expiry(0)
            return htmx_redirect(request, reverse('accounts:dashboard'))
    return render_htmx(request, 'accounts/login.html', 'accounts/partials/login_content.html', {'form': form})


def verify_email(request, token):
    record = get_object_or_404(EmailVerificationToken, token=token, used_at__isnull=True)
    if record.expires_at < timezone.now():
        return HttpResponseForbidden('Verification link expired.')
    record.user.is_email_verified = True
    record.user.save(update_fields=['is_email_verified'])
    record.used_at = timezone.now()
    record.save(update_fields=['used_at'])
    messages.success(request, 'Email verified, you can login now.')
    return htmx_redirect(request, reverse('accounts:login'))


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def forgot_password(request):
    form = ForgotPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = User.objects.filter(email=form.cleaned_data['email']).first()
        if user:
            token = build_password_reset(user)
            reset_url = request.build_absolute_uri(reverse('accounts:reset_password', kwargs={'token': token.token}))
            send_email_task.delay('Reset password', f'Reset link: {reset_url}', [user.email])
        messages.success(request, 'If the email exists, a reset link has been sent.')
        return htmx_redirect(request, reverse('accounts:login'))
    return render_htmx(request, 'accounts/forgot_password.html', 'accounts/partials/forgot_password_content.html', {'form': form})


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def reset_password(request, token):
    record = get_object_or_404(PasswordResetToken, token=token, used_at__isnull=True)
    form = ResetPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if record.expires_at < timezone.now():
            return HttpResponseForbidden('Reset link expired.')
        record.user.set_password(form.cleaned_data['new_password'])
        record.user.save(update_fields=['password'])
        record.used_at = timezone.now()
        record.save(update_fields=['used_at'])
        messages.success(request, 'Password reset successful. Login again.')
        return htmx_redirect(request, reverse('accounts:login'))
    return render_htmx(request, 'accounts/reset_password.html', 'accounts/partials/reset_password_content.html', {'form': form})


def twofa_challenge(request):
    if request.method == 'POST':
        user = User.objects.filter(id=request.session.get('pre_2fa_user_id')).first()
        if not user:
            return redirect('accounts:login')
        if verify_otp(user.twofa_settings.secret, request.POST.get('otp_code', '')):
            login(request, user)
            request.session.cycle_key()
            request.session.pop('pre_2fa_user_id', None)
            return htmx_redirect(request, reverse('accounts:dashboard'))
        messages.error(request, 'Invalid OTP code.')
    return render_htmx(request, 'accounts/twofa_challenge.html', 'accounts/partials/twofa_challenge_content.html')


@login_required
def logout_view(request):
    if request.method == 'POST':
        auth_logout(request)
    return htmx_redirect(request, reverse('accounts:login'))
