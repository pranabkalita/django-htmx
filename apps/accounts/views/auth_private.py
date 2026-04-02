from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse

from apps.accounts.forms.profile_forms import ProfileForm
from apps.accounts.forms.twofa_forms import OTPVerifyForm
from apps.accounts.services.auth_service import record_security_event
from apps.accounts.services.user_service import deactivate_user, update_profile
from apps.accounts.services import session_service
from apps.accounts.services.twofa_service import generate_secret, get_or_create_twofa, provisioning_uri, qr_data_uri, verify_otp
from apps.common import toasts
from apps.common.views.rendering import htmx_redirect, render_htmx


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@login_required
def dashboard(request):
    twofa = getattr(request.user, 'twofa_settings', None)
    return render_htmx(
        request,
        'accounts/dashboard.html',
        'accounts/partials/dashboard_content.html',
        {'twofa_enabled': bool(twofa and twofa.is_enabled)},
    )


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, initial={'first_name': request.user.first_name, 'last_name': request.user.last_name})
    if request.method == 'POST' and form.is_valid():
        update_profile(request.user, form.cleaned_data['first_name'], form.cleaned_data['last_name'])
        toasts.success(request, 'Profile updated.')
        if request.headers.get('HX-Request') == 'true':
            refreshed_form = ProfileForm(initial={'first_name': request.user.first_name, 'last_name': request.user.last_name})
            return render_htmx(
                request,
                'accounts/account/profile.html',
                'accounts/account/partials/profile_content.html',
                {'form': refreshed_form},
            )
        return htmx_redirect(request, reverse('accounts:profile'))
    if request.method == 'POST' and not form.is_valid():
        toasts.error(request, 'Please correct the profile form errors and try again.')
    return render_htmx(request, 'accounts/account/profile.html', 'accounts/account/partials/profile_content.html', {'form': form})


@login_required
def change_password(request):
    form = PasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        logout(request)
        toasts.success(request, 'Password changed. Login again.')
        return htmx_redirect(request, reverse('accounts:login'))
    return render_htmx(request, 'accounts/account/change_password.html', 'accounts/account/partials/change_password_content.html', {'form': form})


@login_required
def twofa_settings(request):
    twofa = get_or_create_twofa(request.user)
    otp_form = OTPVerifyForm(request.POST or None)
    qr_uri = None

    if request.method == 'POST' and request.POST.get('action') == 'start_enable':
        twofa.secret = generate_secret()
        twofa.save(update_fields=['secret'])

    if twofa.secret and not twofa.is_enabled:
        qr_uri = qr_data_uri(provisioning_uri(request.user, twofa.secret))

    if request.method == 'POST' and request.POST.get('action') == 'confirm_enable' and otp_form.is_valid():
        if verify_otp(twofa.secret, otp_form.cleaned_data['otp_code']):
            twofa.is_enabled = True
            twofa.save(update_fields=['is_enabled'])
            record_security_event(event_type='twofa_enabled', user=request.user, ip_address=_client_ip(request))
            toasts.success(request, '2FA enabled.')
            return htmx_redirect(request, reverse('accounts:twofa_settings'))
        toasts.error(request, 'Invalid OTP code.')

    if request.method == 'POST' and request.POST.get('action') == 'disable' and otp_form.is_valid():
        if verify_otp(twofa.secret, otp_form.cleaned_data['otp_code']):
            twofa.is_enabled = False
            twofa.secret = ''
            twofa.save(update_fields=['is_enabled', 'secret'])
            record_security_event(event_type='twofa_disabled', user=request.user, ip_address=_client_ip(request))
            toasts.success(request, '2FA disabled.')
            return htmx_redirect(request, reverse('accounts:twofa_settings'))
        toasts.error(request, 'Invalid OTP code.')

    return render_htmx(
        request,
        'accounts/account/twofa.html',
        'accounts/account/partials/twofa_content.html',
        {'twofa': twofa, 'otp_form': otp_form, 'qr_uri': qr_uri},
    )


@login_required
def deactivate_account(request):
    if request.method == 'POST':
        password = request.POST.get('password', '')
        if not request.user.check_password(password):
            toasts.error(request, 'Incorrect password. Account not deactivated.')
        else:
            deactivate_user(request.user)
            record_security_event(event_type='account_deactivated', user=request.user, ip_address=_client_ip(request))
            logout(request)
            toasts.warning(request, 'Account deactivated. You have been logged out.', position='top-center')
            return htmx_redirect(request, reverse('accounts:login'))
    return render_htmx(request, 'accounts/account/deactivate.html', 'accounts/account/partials/deactivate_content.html')


@login_required
def sessions_list(request):
    sessions = session_service.get_user_sessions(request.user.id, request.session.session_key)
    return render_htmx(request, 'accounts/account/sessions.html', None, {'sessions': sessions})


@login_required
def revoke_session_view(request):
    if request.method == 'POST':
        session_key = request.POST.get('session_key', '')
        if session_key:
            revoked = session_service.revoke_session(session_key, request.user.id)
            if revoked:
                toasts.success(request, 'Session revoked successfully.')
            else:
                toasts.warning(request, 'Session already expired or unavailable.')
    return htmx_redirect(request, reverse('accounts:sessions'))


@login_required
def revoke_all_sessions_view(request):
    if request.method == 'POST':
        # Revoke all sessions including current — logs user out of all devices.
        session_service.revoke_all_sessions(request.user.id)
        logout(request)
        toasts.warning(request, 'Logged out from all sessions.', position='top-center')
        return htmx_redirect(request, reverse('accounts:login'))
    return htmx_redirect(request, reverse('accounts:sessions'))


@login_required
def logout_view(request):
    if request.method == 'POST':
        logout(request)
        toasts.info(request, 'You have been logged out.')
    return htmx_redirect(request, reverse('accounts:login'))
