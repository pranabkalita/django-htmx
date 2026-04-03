from django.contrib.auth import logout
from django.urls import reverse

from apps.common import toasts
from apps.common.session_timeout import (
    ensure_session_tracking,
    is_absolute_timed_out,
    is_idle_timed_out,
    touch_authenticated_session,
)
from apps.common.views.rendering import htmx_redirect


class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, 'user', None) and request.user.is_authenticated:
            session_state = ensure_session_tracking(request.session)
            if is_absolute_timed_out(session_state):
                return self._expire_session(request, 'Session expired. Please sign in again.')
            if is_idle_timed_out(session_state):
                return self._expire_session(request, 'Session expired due to inactivity. Please sign in again.')

        response = self.get_response(request)

        if getattr(request, 'user', None) and request.user.is_authenticated:
            touch_authenticated_session(request.session)

        return response

    def _expire_session(self, request, message):
        logout(request)
        toasts.warning(request, message, position='top-center')
        return htmx_redirect(request, reverse('accounts:login'), shell='guest')
