from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse

from apps.accounts.forms.profile_forms import ProfileForm
from apps.accounts.forms.twofa_forms import OTPVerifyForm
from apps.accounts.services.twofa_service import generate_secret, get_or_create_twofa, provisioning_uri, qr_data_uri, verify_otp
from apps.common.views.rendering import htmx_redirect, render_htmx


@login_required
def dashboard(request):
    return render_htmx(request, 'accounts/dashboard.html', 'accounts/partials/dashboard_content.html')


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, initial={'first_name': request.user.first_name, 'last_name': request.user.last_name})
    if request.method == 'POST' and form.is_valid():
        request.user.first_name = form.cleaned_data['first_name']
        request.user.last_name = form.cleaned_data['last_name']
        request.user.save(update_fields=['first_name', 'last_name'])
        messages.success(request, 'Profile updated.')
        return htmx_redirect(request, reverse('accounts:profile'))
    return render_htmx(request, 'accounts/account/profile.html', 'accounts/account/partials/profile_content.html', {'form': form})


@login_required
def change_password(request):
    form = PasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        logout(request)
        messages.success(request, 'Password changed. Login again.')
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
            messages.success(request, '2FA enabled.')
            return htmx_redirect(request, reverse('accounts:twofa_settings'))
        messages.error(request, 'Invalid OTP code.')

    if request.method == 'POST' and request.POST.get('action') == 'disable' and otp_form.is_valid():
        if verify_otp(twofa.secret, otp_form.cleaned_data['otp_code']):
            twofa.is_enabled = False
            twofa.secret = ''
            twofa.save(update_fields=['is_enabled', 'secret'])
            messages.success(request, '2FA disabled.')
            return htmx_redirect(request, reverse('accounts:twofa_settings'))
        messages.error(request, 'Invalid OTP code.')

    return render_htmx(
        request,
        'accounts/account/twofa.html',
        'accounts/account/partials/twofa_content.html',
        {'twofa': twofa, 'otp_form': otp_form, 'qr_uri': qr_uri},
    )


@login_required
def deactivate_account(request):
    if request.method == 'POST':
        request.user.is_active = False
        request.user.save(update_fields=['is_active'])
        logout(request)
        return htmx_redirect(request, reverse('accounts:login'))
    return render_htmx(request, 'accounts/account/deactivate.html', 'accounts/account/partials/deactivate_content.html')
