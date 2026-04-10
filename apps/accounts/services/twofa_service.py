import base64
import io
from datetime import timedelta

import pyotp
import qrcode
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import TwoFactorSettings


def get_or_create_twofa(user):
    twofa = TwoFactorSettings.all_objects.filter(user=user).first()
    if twofa:
        if twofa.is_deleted:
            twofa.restore()
        return twofa
    twofa = TwoFactorSettings.objects.create(user=user, created_by=user)
    return twofa


def generate_secret():
    return pyotp.random_base32()


def provisioning_uri(user, secret):
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=settings.APP_NAME)


def qr_data_uri(uri):
    image = qrcode.make(uri)
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def verify_otp(secret, code):
    """Pure OTP verification without replay protection. Use consume_otp for login flows."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def consume_otp(twofa, code):
    """Verify OTP and record use timestamp to prevent replay within the valid window.

    A TOTP code with valid_window=1 is valid across a ±1 step window (90 seconds total).
    If a code was already consumed within that window, this returns False even if the
    code itself would otherwise verify, preventing replay attacks.
    """
    now = timezone.now()
    if twofa.last_otp_at is not None and (now - twofa.last_otp_at) < timedelta(seconds=90):
        return False
    if not pyotp.TOTP(twofa.secret).verify(code, valid_window=1):
        return False
    twofa.last_otp_at = now
    twofa.save(update_fields=['last_otp_at'])
    return True
