import secrets
import hashlib
import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import caches
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, PasswordResetToken, SecurityEvent, User
from apps.accounts.services.audit_log_service import log_activity


def normalize_email_input(email):
    return (email or '').strip().lower()


def hash_link_token(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


def token_lookup_candidates(raw_token):
    """Return canonical stored lookup values for auth link tokens."""
    normalized = (raw_token or '').strip()
    if not normalized:
        return []
    return [hash_link_token(normalized)]


def _normalized_email_lock_key(email):
    return normalize_email_input(email) or '__empty__'


def _auth_cache():
    return caches['default']


def get_login_lock_seconds(email):
    key = _normalized_email_lock_key(email)
    unlock_at = _auth_cache().get(f'auth:login:lock:{key}')
    if not unlock_at:
        return 0
    remaining = int(unlock_at) - int(time.time())
    if remaining <= 0:
        _auth_cache().delete(f'auth:login:lock:{key}')
        return 0
    return remaining


def register_login_failure(email):
    key = _normalized_email_lock_key(email)
    cache = _auth_cache()
    count_key = f'auth:login:fail:{key}'
    lock_key = f'auth:login:lock:{key}'

    failures = int(cache.get(count_key, 0)) + 1
    cache.set(count_key, failures, timeout=settings.LOGIN_FAILURE_WINDOW_SECONDS)

    if failures < settings.LOGIN_FAILURE_THRESHOLD:
        return 0

    multiplier = 2 ** (failures - settings.LOGIN_FAILURE_THRESHOLD)
    lock_seconds = min(settings.LOGIN_FAILURE_MAX_LOCK_SECONDS, settings.LOGIN_FAILURE_BASE_LOCK_SECONDS * multiplier)
    unlock_at = int(time.time()) + int(lock_seconds)
    cache.set(lock_key, unlock_at, timeout=lock_seconds)
    return int(lock_seconds)


def clear_login_failures(email):
    key = _normalized_email_lock_key(email)
    cache = _auth_cache()
    cache.delete_many([f'auth:login:fail:{key}', f'auth:login:lock:{key}'])


def purge_expired_auth_tokens(*, now_ts=None):
    now_ts = now_ts or timezone.now()
    ev_qs = EmailVerificationToken.objects.filter(
        Q(used_at__isnull=False) | Q(expires_at__lt=now_ts)
    )
    ev_qs.filter(used_at__isnull=True).update(used_at=now_ts)
    ev_deleted = ev_qs.soft_delete(deleted_at=now_ts)

    pr_qs = PasswordResetToken.objects.filter(
        Q(used_at__isnull=False) | Q(expires_at__lt=now_ts)
    )
    pr_qs.filter(used_at__isnull=True).update(used_at=now_ts)
    pr_deleted = pr_qs.soft_delete(deleted_at=now_ts)

    if ev_deleted:
        log_activity(
            action='email_verification_tokens_soft_deleted',
            entity_type='accounts.emailverificationtoken',
            metadata={'count': ev_deleted, 'reason': 'expired_or_used_cleanup'},
        )
    if pr_deleted:
        log_activity(
            action='password_reset_tokens_soft_deleted',
            entity_type='accounts.passwordresettoken',
            metadata={'count': pr_deleted, 'reason': 'expired_or_used_cleanup'},
        )

    return {'email_verification_deleted': ev_deleted, 'password_reset_deleted': pr_deleted}


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
    event = SecurityEvent.objects.create(
        user=user,
        created_by=user,
        event_type=event_type,
        ip_address=ip_address,
    )
    log_activity(
        action=event_type,
        actor=user,
        entity=event,
        ip_address=ip_address,
        metadata={'source': 'security_event'},
    )
    return event


def register_user(*, email, first_name, last_name, password, actor=None):
    user = User.objects.create_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
        created_by=actor,
    )
    log_activity(action='user_registered', actor=actor or user, entity=user)
    return user


def build_email_verification(user, *, actor=None):
    now_ts = timezone.now()
    active_qs = EmailVerificationToken.objects.filter(user=user, used_at__isnull=True)
    active_qs.update(used_at=now_ts)
    active_qs.soft_delete(deleted_by=actor or user, deleted_at=now_ts)

    raw_token = secrets.token_urlsafe(32)
    record = EmailVerificationToken.objects.create(
        user=user,
        created_by=actor or user,
        token=hash_link_token(raw_token),
        expires_at=EmailVerificationToken.default_expiry(),
    )
    record.raw_token = raw_token
    log_activity(
        action='email_verification_token_created',
        actor=actor or user,
        entity=record,
        metadata={'user_id': user.id},
    )
    return record


def build_password_reset(user, *, actor=None):
    now_ts = timezone.now()
    active_qs = PasswordResetToken.objects.filter(user=user, used_at__isnull=True)
    active_qs.update(used_at=now_ts)
    active_qs.soft_delete(deleted_by=actor or user, deleted_at=now_ts)

    raw_token = secrets.token_urlsafe(32)
    record = PasswordResetToken.objects.create(
        user=user,
        created_by=actor or user,
        token=hash_link_token(raw_token),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    record.raw_token = raw_token
    log_activity(
        action='password_reset_token_created',
        actor=actor or user,
        entity=record,
        metadata={'user_id': user.id},
    )
    return record


def complete_password_reset(record, new_password, *, actor=None):
    record.user.set_password(new_password)
    record.user.save(update_fields=['password'])
    used_at = timezone.now()
    record.used_at = used_at
    record.save(update_fields=['used_at', 'updated_at'])
    record.soft_delete(deleted_by=actor or record.user, deleted_at=used_at)
    log_activity(
        action='password_reset_completed',
        actor=actor or record.user,
        entity=record.user,
        metadata={'token_id': record.id},
    )
