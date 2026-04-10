from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services.audit_log_service import log_activity


def get_user_sessions(user_id, current_session_key):
    """Return a list of session dicts for the given user, current session first."""
    user_id_str = str(user_id)
    active_sessions = Session.objects.filter(expire_date__gt=timezone.now())
    results = []
    for session in active_sessions:
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if data.get('_auth_user_id') == user_id_str:
            results.append({
                'session_key': session.session_key,
                'expire_date': session.expire_date,
                'is_current': session.session_key == current_session_key,
            })
    results.sort(key=lambda s: (not s['is_current'], s['expire_date']))
    return results


def revoke_session(session_key, user_id, *, actor=None):
    """Delete a session only if it belongs to the given user. Returns True on success."""
    user_id_str = str(user_id)
    try:
        session = Session.objects.get(session_key=session_key)
        if session.get_decoded().get('_auth_user_id') == user_id_str:
            session.delete()
            target_user = actor or User.objects.filter(id=user_id).first()
            log_activity(
                action='session_revoked',
                actor=target_user,
                entity_type='django.session',
                entity_id=session_key,
                metadata={'target_user_id': user_id},
            )
            return True
    except Session.DoesNotExist:
        pass
    return False


def revoke_all_sessions(user_id, except_key=None, *, actor=None):
    """Delete all sessions for the user. Optionally keep one session by key."""
    user_id_str = str(user_id)
    active_sessions = Session.objects.filter(expire_date__gt=timezone.now())
    count = 0
    for session in active_sessions:
        if except_key and session.session_key == except_key:
            continue
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if data.get('_auth_user_id') == user_id_str:
            session.delete()
            count += 1
    if count:
        target_user = actor or User.objects.filter(id=user_id).first()
        log_activity(
            action='all_sessions_revoked',
            actor=target_user,
            entity_type='accounts.user',
            entity_id=user_id,
            metadata={'revoked_count': count, 'except_key': except_key or ''},
        )
    return count
