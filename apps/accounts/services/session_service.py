from django.contrib.sessions.models import Session
from django.utils import timezone


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


def revoke_session(session_key, user_id):
    """Delete a session only if it belongs to the given user. Returns True on success."""
    user_id_str = str(user_id)
    try:
        session = Session.objects.get(session_key=session_key)
        if session.get_decoded().get('_auth_user_id') == user_id_str:
            session.delete()
            return True
    except Session.DoesNotExist:
        pass
    return False


def revoke_all_sessions(user_id, except_key=None):
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
    return count
