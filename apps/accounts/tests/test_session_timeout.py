from datetime import timedelta

import pyotp
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services.twofa_service import get_or_create_twofa
from apps.common.session_timeout import (
    SESSION_BROWSER_CLOSE_KEY,
    SESSION_LAST_ACTIVITY_AT_KEY,
    SESSION_STARTED_AT_KEY,
)

from .mixins import HTMXAssertionsMixin


class SessionTimeoutMiddlewareTests(HTMXAssertionsMixin, TestCase):
    @override_settings(SESSION_IDLE_TIMEOUT=60, SESSION_ABSOLUTE_TIMEOUT=3600)
    def test_idle_timeout_logs_out_authenticated_htmx_request(self):
        user = User.objects.create_user(
            email='idle@example.com',
            first_name='Idle',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )
        self.client.force_login(user)

        session = self.client.session
        now_ts = int(timezone.now().timestamp())
        session[SESSION_STARTED_AT_KEY] = now_ts - 300
        session[SESSION_LAST_ACTIVITY_AT_KEY] = now_ts - 61
        session[SESSION_BROWSER_CLOSE_KEY] = False
        session.save()

        response = self.client.get(reverse('accounts:dashboard'), HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    @override_settings(SESSION_IDLE_TIMEOUT=120, SESSION_ABSOLUTE_TIMEOUT=3600)
    def test_active_request_slides_last_activity_forward(self):
        user = User.objects.create_user(
            email='sliding@example.com',
            first_name='Sliding',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )
        self.client.force_login(user)

        session = self.client.session
        now_ts = int(timezone.now().timestamp())
        session[SESSION_STARTED_AT_KEY] = now_ts - 300
        session[SESSION_LAST_ACTIVITY_AT_KEY] = now_ts - 30
        session[SESSION_BROWSER_CLOSE_KEY] = False
        session.save()

        self.client.get(reverse('accounts:dashboard'))

        updated_session = self.client.session
        self.assertGreater(updated_session[SESSION_LAST_ACTIVITY_AT_KEY], now_ts - 30)
        self.assertLessEqual(updated_session.get_expiry_age(), 120)

    @override_settings(SESSION_IDLE_TIMEOUT=300, SESSION_ABSOLUTE_TIMEOUT=60)
    def test_absolute_timeout_overrides_recent_activity(self):
        user = User.objects.create_user(
            email='absolute@example.com',
            first_name='Absolute',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )
        self.client.force_login(user)

        session = self.client.session
        now_ts = int(timezone.now().timestamp())
        session[SESSION_STARTED_AT_KEY] = now_ts - 61
        session[SESSION_LAST_ACTIVITY_AT_KEY] = now_ts - 1
        session[SESSION_BROWSER_CLOSE_KEY] = False
        session.save()

        response = self.client.get(reverse('accounts:dashboard'), HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_twofa_login_without_remember_me_keeps_browser_close_expiry(self):
        user = User.objects.create_user(
            email='twofa-browser@example.com',
            first_name='Two',
            last_name='Browser',
            password='StrongPass123!',
            is_email_verified=True,
        )
        twofa = get_or_create_twofa(user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = True
        twofa.save(update_fields=['secret', 'is_enabled'])

        login_response = self.client.post(
            reverse('accounts:login'),
            {'email': user.email, 'password': 'StrongPass123!', 'remember_me': False},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(login_response.status_code, 204)
        self.assert_hx_location(login_response, reverse('accounts:twofa_challenge'))

        otp = pyotp.TOTP(twofa.secret).now()
        challenge_response = self.client.post(
            reverse('accounts:twofa_challenge'),
            {'otp_code': otp},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(challenge_response.status_code, 204)
        self.assert_hx_location(challenge_response, reverse('accounts:dashboard'))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_htmx_dashboard_from_guest_shell_swaps_full_auth_layout(self):
        user = User.objects.create_user(
            email='layout@example.com',
            first_name='Layout',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse('accounts:dashboard'),
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('HX-Retarget'), 'body')
        self.assertEqual(response.headers.get('HX-Reswap'), 'innerHTML')
        self.assertContains(response, 'Security Dashboard')
