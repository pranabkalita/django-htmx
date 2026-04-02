import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, PasswordResetToken


def authenticate_user(email, password):
    return authenticate(email=email, password=password)


def build_email_verification(user):
    token = secrets.token_urlsafe(32)
    return EmailVerificationToken.objects.create(user=user, token=token, expires_at=EmailVerificationToken.default_expiry())


def build_password_reset(user):
    token = secrets.token_urlsafe(32)
    return PasswordResetToken.objects.create(user=user, token=token, expires_at=timezone.now() + timedelta(hours=1))
