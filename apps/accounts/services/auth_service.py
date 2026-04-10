import secrets
from datetime import timedelta

from django.contrib.auth import authenticate
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, PasswordResetToken, SecurityEvent, User


def normalize_email_input(email):
    return (email or '').strip().lower()


def authenticate_user(email, password):
    normalized_email = normalize_email_input(email)
    user = authenticate(email=normalized_email, password=password)
    if user:
        return User.objects.select_related('twofa_settings').filter(id=user.id).first()

    # Legacy rows may contain mixed-case emails in case-sensitive databases.
    candidate = User.objects.filter(email__iexact=normalized_email).first()
    if not candidate or not candidate.check_password(password) or not candidate.is_active:
        return None
    return User.objects.select_related('twofa_settings').filter(id=candidate.id).first()


def record_security_event(*, event_type, user=None, ip_address=None):
    return SecurityEvent.objects.create(user=user, event_type=event_type, ip_address=ip_address)


def register_user(*, email, first_name, last_name, password):
    return User.objects.create_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
    )


def build_email_verification(user):
    EmailVerificationToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
    token = secrets.token_urlsafe(32)
    return EmailVerificationToken.objects.create(user=user, token=token, expires_at=EmailVerificationToken.default_expiry())


def build_password_reset(user):
    PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
    token = secrets.token_urlsafe(32)
    return PasswordResetToken.objects.create(user=user, token=token, expires_at=timezone.now() + timedelta(hours=1))


def complete_password_reset(record, new_password):
    record.user.set_password(new_password)
    record.user.is_active = True
    record.user.save(update_fields=['password', 'is_active'])
    record.used_at = timezone.now()
    record.save(update_fields=['used_at'])
