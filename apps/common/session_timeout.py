from django.conf import settings
from django.utils import timezone

SESSION_STARTED_AT_KEY = '_session_started_at'
SESSION_LAST_ACTIVITY_AT_KEY = '_session_last_activity_at'
SESSION_BROWSER_CLOSE_KEY = '_session_browser_close'


def _now_ts():
    return int(timezone.now().timestamp())


def initialize_authenticated_session(request, *, browser_close=False):
    now_ts = _now_ts()
    request.session[SESSION_STARTED_AT_KEY] = now_ts
    request.session[SESSION_LAST_ACTIVITY_AT_KEY] = now_ts
    request.session[SESSION_BROWSER_CLOSE_KEY] = bool(browser_close)
    apply_session_expiry(request.session, now_ts=now_ts)


def ensure_session_tracking(session):
    now_ts = _now_ts()
    changed = False

    if SESSION_STARTED_AT_KEY not in session:
        session[SESSION_STARTED_AT_KEY] = now_ts
        changed = True
    if SESSION_LAST_ACTIVITY_AT_KEY not in session:
        session[SESSION_LAST_ACTIVITY_AT_KEY] = now_ts
        changed = True
    if SESSION_BROWSER_CLOSE_KEY not in session:
        session[SESSION_BROWSER_CLOSE_KEY] = False
        changed = True

    if changed:
        apply_session_expiry(session, now_ts=now_ts)

    return {
        'now_ts': now_ts,
        'started_at': int(session[SESSION_STARTED_AT_KEY]),
        'last_activity_at': int(session[SESSION_LAST_ACTIVITY_AT_KEY]),
        'browser_close': bool(session[SESSION_BROWSER_CLOSE_KEY]),
    }


def absolute_deadline_ts(session):
    started_at = int(session.get(SESSION_STARTED_AT_KEY, _now_ts()))
    return started_at + settings.SESSION_ABSOLUTE_TIMEOUT


def is_idle_timed_out(session_state):
    return session_state['now_ts'] - session_state['last_activity_at'] >= settings.SESSION_IDLE_TIMEOUT


def is_absolute_timed_out(session_state):
    return session_state['now_ts'] - session_state['started_at'] >= settings.SESSION_ABSOLUTE_TIMEOUT


def touch_authenticated_session(session, *, now_ts=None):
    now_ts = now_ts if now_ts is not None else _now_ts()
    session[SESSION_LAST_ACTIVITY_AT_KEY] = now_ts
    apply_session_expiry(session, now_ts=now_ts)


def apply_session_expiry(session, *, now_ts=None):
    now_ts = now_ts if now_ts is not None else _now_ts()
    if bool(session.get(SESSION_BROWSER_CLOSE_KEY, False)):
        session.set_expiry(0)
        return

    remaining_absolute = max(1, absolute_deadline_ts(session) - now_ts)
    session.set_expiry(min(settings.SESSION_IDLE_TIMEOUT, remaining_absolute))
