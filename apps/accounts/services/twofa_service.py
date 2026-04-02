import base64
import io

import pyotp
import qrcode

from apps.accounts.models import TwoFactorSettings


def get_or_create_twofa(user):
    twofa, _ = TwoFactorSettings.objects.get_or_create(user=user)
    return twofa


def generate_secret():
    return pyotp.random_base32()


def provisioning_uri(user, secret):
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name='SecureDjangoHTMX')


def qr_data_uri(uri):
    image = qrcode.make(uri)
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def verify_otp(secret, code):
    return pyotp.TOTP(secret).verify(code, valid_window=1)
