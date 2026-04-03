from datetime import timedelta

import pyotp
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SecurityEvent, TwoFactorSettings, User
from apps.accounts.services.twofa_service import get_or_create_twofa

from .mixins import HTMXAssertionsMixin


def create_session_for_user(user_id, *, expire_in_seconds=3600):
    session = SessionStore()
    session['_auth_user_id'] = str(user_id)
    session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
    session['_auth_user_hash'] = 'hash'
    session.set_expiry(expire_in_seconds)
    session.save()
    return session.session_key


class AuthPrivateViewTests(HTMXAssertionsMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='private@example.com',
            first_name='Private',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_profile_update_success(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:profile'),
            {'first_name': 'Updated', 'last_name': 'Name'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.last_name, 'Name')

    def test_profile_update_invalid_form_shows_error(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:profile'),
            {'first_name': '', 'last_name': 'Name'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please correct the profile form errors and try again.')

    def test_change_password_logs_user_out(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:change_password'),
            {
                'old_password': 'StrongPass123!',
                'new_password1': 'NewStrongPass123!@',
                'new_password2': 'NewStrongPass123!@',
            },
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/change-password/',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'), target='body', swap='innerHTML')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_twofa_start_enable_generates_secret(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:twofa_settings'), {'action': 'start_enable'})
        self.assertEqual(response.status_code, 200)
        twofa = TwoFactorSettings.objects.get(user=self.user)
        self.assertTrue(twofa.secret)
        self.assertFalse(twofa.is_enabled)

    def test_twofa_confirm_enable_invalid_code(self):
        self.client.force_login(self.user)
        twofa = get_or_create_twofa(self.user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = False
        twofa.save(update_fields=['secret', 'is_enabled'])

        response = self.client.post(reverse('accounts:twofa_settings'), {'action': 'confirm_enable', 'otp_code': '000000'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid OTP code.')
        twofa.refresh_from_db()
        self.assertFalse(twofa.is_enabled)

    def test_twofa_confirm_enable_success_records_event(self):
        self.client.force_login(self.user)
        twofa = get_or_create_twofa(self.user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = False
        twofa.save(update_fields=['secret', 'is_enabled'])
        otp = pyotp.TOTP(twofa.secret).now()

        response = self.client.post(
            reverse('accounts:twofa_settings'),
            {'action': 'confirm_enable', 'otp_code': otp},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:twofa_settings'))
        twofa.refresh_from_db()
        self.assertTrue(twofa.is_enabled)
        self.assertTrue(SecurityEvent.objects.filter(event_type='twofa_enabled', user=self.user).exists())

    def test_twofa_disable_success_clears_secret_and_records_event(self):
        self.client.force_login(self.user)
        twofa = get_or_create_twofa(self.user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = True
        twofa.save(update_fields=['secret', 'is_enabled'])
        otp = pyotp.TOTP(twofa.secret).now()

        response = self.client.post(
            reverse('accounts:twofa_settings'),
            {'action': 'disable', 'otp_code': otp},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:twofa_settings'))
        twofa.refresh_from_db()
        self.assertFalse(twofa.is_enabled)
        self.assertEqual(twofa.secret, '')
        self.assertTrue(SecurityEvent.objects.filter(event_type='twofa_disabled', user=self.user).exists())

    def test_deactivate_account_wrong_password(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:deactivate_account'), {'password': 'wrong-password'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect password. Account not deactivated.')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_deactivate_account_success_logs_out(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:deactivate_account'),
            {'password': 'StrongPass123!'},
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/deactivate/',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'), target='body', swap='innerHTML')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertTrue(SecurityEvent.objects.filter(event_type='account_deactivated', user=self.user).exists())

    def test_session_list_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:sessions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active Sessions')

    def test_revoke_single_session_deletes_target(self):
        self.client.force_login(self.user)
        target_key = create_session_for_user(self.user.id)
        response = self.client.post(
            reverse('accounts:revoke_session'),
            {'session_key': target_key},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:sessions'))
        self.assertFalse(Session.objects.filter(session_key=target_key).exists())

    def test_revoke_all_sessions_logs_out_current_user(self):
        self.client.force_login(self.user)
        extra_key = create_session_for_user(self.user.id)

        response = self.client.post(
            reverse('accounts:revoke_all_sessions'),
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/sessions/',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'), target='body', swap='innerHTML')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFalse(Session.objects.filter(session_key=extra_key).exists())

    def test_logout_view_always_redirects_login(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:logout'),
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/dashboard/',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'), target='body', swap='innerHTML')
