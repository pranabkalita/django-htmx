from datetime import timedelta
from unittest.mock import patch

import pyotp
from django.core.cache import caches
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, PasswordResetToken, SecurityEvent, User
from apps.accounts.services.auth_service import hash_link_token
from apps.accounts.services.twofa_service import get_or_create_twofa
from apps.common.session_timeout import (
    SESSION_BROWSER_CLOSE_KEY,
    SESSION_LAST_ACTIVITY_AT_KEY,
    SESSION_STARTED_AT_KEY,
)

from .mixins import HTMXAssertionsMixin


class AuthPublicViewTests(HTMXAssertionsMixin, TestCase):
    def setUp(self):
        caches['default'].clear()
        self.verified_user = User.objects.create_user(
            email='verified@example.com',
            first_name='Verified',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )
        self.unverified_user = User.objects.create_user(
            email='pending@example.com',
            first_name='Pending',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=False,
        )

    def test_register_authenticated_user_redirects_dashboard(self):
        self.client.force_login(self.verified_user)
        response = self.client.get(reverse('accounts:register'))
        self.assertRedirects(response, reverse('accounts:dashboard'))

    @patch('apps.accounts.views.auth_public.enqueue_email_job')
    def test_register_success_creates_user_token_and_enqueues_email(self, mock_delay):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'New',
                'last_name': 'User',
                'email': 'new@example.com',
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
            },
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/register/',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertTrue(User.objects.filter(email='new@example.com').exists())
        self.assertEqual(EmailVerificationToken.objects.filter(user__email='new@example.com', used_at__isnull=True).count(), 1)
        mock_delay.assert_called_once()

    def test_register_duplicate_email_redirects_with_generic_message(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Duplicate',
                'last_name': 'User',
                'email': self.verified_user.email,
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
            },
        )
        self.assertRedirects(response, reverse('accounts:login'))

    def test_register_duplicate_email_with_case_variation_redirects_with_generic_message(self):
        response = self.client.post(
            reverse('accounts:register'),
            {
                'first_name': 'Duplicate',
                'last_name': 'User',
                'email': 'Verified@Example.com',
                'password': 'StrongPass123!',
                'confirm_password': 'StrongPass123!',
            },
        )
        self.assertRedirects(response, reverse('accounts:login'))

    def test_login_invalid_credentials_records_security_event(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'wrong-pass', 'remember_me': True},
            HTTP_X_FORWARDED_FOR='198.51.100.42',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid credentials.')
        event = SecurityEvent.objects.filter(event_type='login_failed').latest('id')
        self.assertEqual(event.ip_address, '127.0.0.1')

    @override_settings(
        LOGIN_FAILURE_THRESHOLD=2,
        LOGIN_FAILURE_BASE_LOCK_SECONDS=60,
        LOGIN_FAILURE_MAX_LOCK_SECONDS=60,
        LOGIN_FAILURE_WINDOW_SECONDS=300,
    )
    def test_login_lockout_after_repeated_failures(self):
        self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'wrong-pass', 'remember_me': True},
        )
        second = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'wrong-pass', 'remember_me': True},
        )
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'Too many failed attempts. Try again in')

        locked = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'StrongPass123!', 'remember_me': True},
        )
        self.assertEqual(locked.status_code, 200)
        self.assertContains(locked, 'Too many failed attempts. Try again in')
        self.assertTrue(SecurityEvent.objects.filter(event_type='login_locked', user=self.verified_user).exists())

    @override_settings(
        LOGIN_FAILURE_THRESHOLD=2,
        LOGIN_FAILURE_BASE_LOCK_SECONDS=60,
        LOGIN_FAILURE_MAX_LOCK_SECONDS=60,
        LOGIN_FAILURE_WINDOW_SECONDS=300,
    )
    def test_login_success_clears_failure_counter(self):
        self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'wrong-pass', 'remember_me': True},
        )
        success = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'StrongPass123!', 'remember_me': True},
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/login/',
        )
        self.assertEqual(success.status_code, 204)
        self.client.logout()

        # One additional failure should not lock because prior counter was reset.
        failure = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'wrong-pass', 'remember_me': True},
        )
        self.assertEqual(failure.status_code, 200)
        self.assertContains(failure, 'Invalid credentials.')

    @override_settings(TRUSTED_PROXY_IPS=['127.0.0.1'])
    def test_login_invalid_credentials_uses_forwarded_ip_for_trusted_proxy(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'wrong-pass', 'remember_me': True},
            HTTP_X_FORWARDED_FOR='198.51.100.42',
        )

        self.assertEqual(response.status_code, 200)
        event = SecurityEvent.objects.filter(event_type='login_failed').latest('id')
        self.assertEqual(event.ip_address, '198.51.100.42')

    def test_login_unverified_user_blocked(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.unverified_user.email, 'password': 'StrongPass123!', 'remember_me': True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please verify your email before login.')
        self.assertTrue(SecurityEvent.objects.filter(event_type='login_blocked_unverified', user=self.unverified_user).exists())

    def test_login_success_sets_session_tracking(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'StrongPass123!', 'remember_me': True},
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/login/',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:dashboard'), target='body', swap='innerHTML')
        session = self.client.session
        self.assertIn(SESSION_STARTED_AT_KEY, session)
        self.assertIn(SESSION_LAST_ACTIVITY_AT_KEY, session)
        self.assertFalse(session.get(SESSION_BROWSER_CLOSE_KEY, True))
        self.assertTrue(SecurityEvent.objects.filter(event_type='login_success', user=self.verified_user).exists())

    def test_login_success_with_mixed_case_and_whitespace_email(self):
        response = self.client.post(
            reverse('accounts:login'),
            {'email': '  Verified@Example.com  ', 'password': 'StrongPass123!', 'remember_me': True},
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/login/',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:dashboard'), target='body', swap='innerHTML')
        self.assertTrue(SecurityEvent.objects.filter(event_type='login_success', user=self.verified_user).exists())

    def test_login_with_2fa_routes_to_challenge(self):
        twofa = get_or_create_twofa(self.verified_user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = True
        twofa.save(update_fields=['secret', 'is_enabled'])

        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'StrongPass123!', 'remember_me': False},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:twofa_challenge'))
        session = self.client.session
        self.assertEqual(session.get('pre_2fa_user_id'), self.verified_user.id)
        self.assertIn('pre_2fa_expires_at', session)
        self.assertFalse(session.get('pre_2fa_remember_me'))

    def test_verify_email_success_marks_user_verified(self):
        raw_token = 'verify-token'
        token = EmailVerificationToken.objects.create(
            user=self.unverified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.get(reverse('accounts:verify_email', kwargs={'token': raw_token}))
        self.assertRedirects(response, reverse('accounts:login'))
        self.unverified_user.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(self.unverified_user.is_email_verified)
        self.assertIsNotNone(token.used_at)

    def test_verify_email_rejects_malformed_token_with_extra_equals(self):
        raw_token = 'verifytoken123'
        token = EmailVerificationToken.objects.create(
            user=self.unverified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.get(reverse('accounts:verify_email', kwargs={'token': 'verify=token123'}))
        self.assertEqual(response.status_code, 404)
        self.unverified_user.refresh_from_db()
        token.refresh_from_db()
        self.assertFalse(self.unverified_user.is_email_verified)
        self.assertIsNone(token.used_at)

    def test_verify_email_expired_token_redirects(self):
        raw_token = 'expired-verify'
        token = EmailVerificationToken.objects.create(
            user=self.unverified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.get(reverse('accounts:verify_email', kwargs={'token': raw_token}))
        self.assertRedirects(response, reverse('accounts:login'))
        self.unverified_user.refresh_from_db()
        self.assertFalse(self.unverified_user.is_email_verified)

    @patch('apps.accounts.views.auth_public.enqueue_email_job')
    def test_forgot_password_existing_email_creates_reset_token(self, mock_delay):
        response = self.client.post(
            reverse('accounts:forgot_password'),
            {'email': self.verified_user.email},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertEqual(PasswordResetToken.objects.filter(user=self.verified_user, used_at__isnull=True).count(), 1)
        mock_delay.assert_called_once()

    @patch('apps.accounts.views.auth_public.enqueue_email_job')
    def test_forgot_password_mixed_case_and_whitespace_email_creates_reset_token(self, mock_delay):
        response = self.client.post(
            reverse('accounts:forgot_password'),
            {'email': '  Verified@Example.com  '},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertEqual(PasswordResetToken.objects.filter(user=self.verified_user, used_at__isnull=True).count(), 1)
        mock_delay.assert_called_once()

    @patch('apps.accounts.views.auth_public.enqueue_email_job')
    def test_forgot_password_unverified_user_sends_verification_instead_of_reset(self, mock_delay):
        response = self.client.post(
            reverse('accounts:forgot_password'),
            {'email': self.unverified_user.email},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertEqual(PasswordResetToken.objects.filter(user=self.unverified_user, used_at__isnull=True).count(), 0)
        self.assertEqual(EmailVerificationToken.objects.filter(user=self.unverified_user, used_at__isnull=True).count(), 1)
        mock_delay.assert_called_once()
        self.assertIn('Verify your account', mock_delay.call_args.kwargs['subject'])

    @patch('apps.accounts.views.auth_public.enqueue_email_job')
    def test_forgot_password_inactive_user_does_not_issue_token_or_email(self, mock_delay):
        self.verified_user.is_active = False
        self.verified_user.save(update_fields=['is_active'])

        response = self.client.post(
            reverse('accounts:forgot_password'),
            {'email': self.verified_user.email},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertEqual(PasswordResetToken.objects.filter(user=self.verified_user, used_at__isnull=True).count(), 0)
        self.assertEqual(EmailVerificationToken.objects.filter(user=self.verified_user, used_at__isnull=True).count(), 0)
        mock_delay.assert_not_called()
        self.assertTrue(SecurityEvent.objects.filter(event_type='password_reset_blocked_inactive', user=self.verified_user).exists())

    @patch('apps.accounts.views.auth_public.enqueue_email_job')
    def test_forgot_password_unknown_email_returns_generic_response(self, mock_delay):
        response = self.client.post(
            reverse('accounts:forgot_password'),
            {'email': 'does-not-exist@example.com'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.assertEqual(PasswordResetToken.objects.count(), 0)
        mock_delay.assert_not_called()

    def test_resend_verification_requires_post(self):
        response = self.client.get(reverse('accounts:resend_verification'))
        self.assertRedirects(response, reverse('accounts:login'))

    @patch('apps.accounts.views.auth_public.enqueue_email_job')
    def test_resend_verification_for_unverified_user_rotates_token(self, mock_delay):
        old = EmailVerificationToken.objects.create(
            user=self.unverified_user,
            token='old-verify-token',
            expires_at=timezone.now() + timedelta(hours=2),
        )
        response = self.client.post(
            reverse('accounts:resend_verification'),
            {'email': self.unverified_user.email},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        old.refresh_from_db()
        self.assertIsNotNone(old.used_at)
        self.assertEqual(EmailVerificationToken.objects.filter(user=self.unverified_user, used_at__isnull=True).count(), 1)
        mock_delay.assert_called_once()

    def test_reset_password_success_updates_password_and_marks_token_used(self):
        raw_token = 'reset-token'
        token = PasswordResetToken.objects.create(
            user=self.verified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse('accounts:reset_password', kwargs={'token': raw_token}),
            {
                'new_password': 'NewStrongPass123!@',
                'confirm_new_password': 'NewStrongPass123!@',
            },
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.verified_user.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(self.verified_user.check_password('NewStrongPass123!@'))
        self.assertIsNotNone(token.used_at)
        self.assertTrue(SecurityEvent.objects.filter(event_type='password_reset_completed', user=self.verified_user).exists())

    def test_reset_password_rejects_malformed_token_with_extra_equals(self):
        raw_token = 'resettoken123'
        token = PasswordResetToken.objects.create(
            user=self.verified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse('accounts:reset_password', kwargs={'token': 'reset=token123'}),
            {
                'new_password': 'NewStrongPass123!@',
                'confirm_new_password': 'NewStrongPass123!@',
            },
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 404)
        self.verified_user.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(self.verified_user.check_password('StrongPass123!'))
        self.assertIsNone(token.used_at)

    def test_reset_password_does_not_verify_user_email(self):
        # User starts unverified
        self.unverified_user.is_email_verified = False
        self.unverified_user.save(update_fields=['is_email_verified'])
        
        raw_token = 'reset-verify-token'
        token = PasswordResetToken.objects.create(
            user=self.unverified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse('accounts:reset_password', kwargs={'token': raw_token}),
            {
                'new_password': 'NewStrongPass123!@',
                'confirm_new_password': 'NewStrongPass123!@',
            },
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.unverified_user.refresh_from_db()
        self.assertFalse(self.unverified_user.is_email_verified)
        self.assertTrue(self.unverified_user.check_password('NewStrongPass123!@'))

    def test_reset_password_preserves_inactive_user_state(self):
        raw_token = 'reset-reactivate-token'
        self.verified_user.is_active = False
        self.verified_user.save(update_fields=['is_active'])

        token = PasswordResetToken.objects.create(
            user=self.verified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse('accounts:reset_password', kwargs={'token': raw_token}),
            {
                'new_password': 'ReactivatedPass123!@',
                'confirm_new_password': 'ReactivatedPass123!@',
            },
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        self.verified_user.refresh_from_db()
        self.assertFalse(self.verified_user.is_active)

        login_response = self.client.post(
            reverse('accounts:login'),
            {'email': self.verified_user.email, 'password': 'ReactivatedPass123!@', 'remember_me': True},
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/account/login/',
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, 'Invalid credentials.')

    def test_login_blocked_after_password_reset_for_unverified_user(self):
        # Start with unverified user
        self.unverified_user.is_email_verified = False
        self.unverified_user.set_password('OldPassword123!')
        self.unverified_user.save(update_fields=['is_email_verified', 'password'])
        
        # Reset password
        raw_token = 'reset-login-token'
        token = PasswordResetToken.objects.create(
            user=self.unverified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        
        from apps.accounts.services.auth_service import complete_password_reset
        complete_password_reset(token, 'NewPassword123!')
        
        # Login should still be blocked while user remains unverified
        response = self.client.post(
            reverse('accounts:login'),
            {'email': self.unverified_user.email, 'password': 'NewPassword123!', 'remember_me': False},
            HTTP_HX_REQUEST='true',
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please verify your email before login.')
        self.assertTrue(SecurityEvent.objects.filter(event_type='login_blocked_unverified', user=self.unverified_user).exists())

    def test_login_blocked_after_password_reset_with_mixed_case_email(self):
        self.unverified_user.is_email_verified = False
        self.unverified_user.set_password('OldPassword123!')
        self.unverified_user.save(update_fields=['is_email_verified', 'password'])

        raw_token = 'reset-login-token-mixed-case'
        token = PasswordResetToken.objects.create(
            user=self.unverified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        from apps.accounts.services.auth_service import complete_password_reset
        complete_password_reset(token, 'NewPassword123!')

        response = self.client.post(
            reverse('accounts:login'),
            {'email': '  Pending@Example.com  ', 'password': 'NewPassword123!', 'remember_me': False},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please verify your email before login.')
        self.assertTrue(SecurityEvent.objects.filter(event_type='login_blocked_unverified', user=self.unverified_user).exists())

    def test_reset_password_expired_token_redirects_to_forgot(self):
        raw_token = 'expired-reset-token'
        token = PasswordResetToken.objects.create(
            user=self.verified_user,
            token=hash_link_token(raw_token),
            expires_at=timezone.now() - timedelta(seconds=10),
        )

        response = self.client.post(
            reverse('accounts:reset_password', kwargs={'token': raw_token}),
            {
                'new_password': 'NewStrongPass123!@',
                'confirm_new_password': 'NewStrongPass123!@',
            },
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:forgot_password'))

    def test_twofa_challenge_expired_window_clears_pre_auth_state(self):
        session = self.client.session
        session['pre_2fa_user_id'] = self.verified_user.id
        session['pre_2fa_expires_at'] = int((timezone.now() - timedelta(minutes=1)).timestamp())
        session['pre_2fa_remember_me'] = True
        session.save()

        response = self.client.post(
            reverse('accounts:twofa_challenge'),
            {'otp_code': '123456'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        session = self.client.session
        self.assertNotIn('pre_2fa_user_id', session)
        self.assertNotIn('pre_2fa_expires_at', session)
        self.assertNotIn('pre_2fa_remember_me', session)

    def test_twofa_challenge_invalid_code_records_failure_event(self):
        twofa = get_or_create_twofa(self.verified_user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = True
        twofa.save(update_fields=['secret', 'is_enabled'])

        session = self.client.session
        session['pre_2fa_user_id'] = self.verified_user.id
        session['pre_2fa_expires_at'] = int((timezone.now() + timedelta(minutes=5)).timestamp())
        session.save()

        response = self.client.post(reverse('accounts:twofa_challenge'), {'otp_code': '000000'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid OTP code.')
        self.assertTrue(SecurityEvent.objects.filter(event_type='twofa_failed', user=self.verified_user).exists())

    def test_twofa_challenge_locks_after_repeated_failures(self):
        twofa = get_or_create_twofa(self.verified_user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = True
        twofa.save(update_fields=['secret', 'is_enabled'])

        session = self.client.session
        session['pre_2fa_user_id'] = self.verified_user.id
        session['pre_2fa_expires_at'] = int((timezone.now() + timedelta(minutes=5)).timestamp())
        session['pre_2fa_remember_me'] = False
        session['pre_2fa_attempts'] = 4
        session.save()

        response = self.client.post(
            reverse('accounts:twofa_challenge'),
            {'otp_code': '000000'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 204)
        self.assert_hx_location(response, reverse('accounts:login'))
        session = self.client.session
        self.assertNotIn('pre_2fa_user_id', session)
        self.assertNotIn('pre_2fa_expires_at', session)
        self.assertNotIn('pre_2fa_remember_me', session)
        self.assertNotIn('pre_2fa_attempts', session)
        self.assertTrue(SecurityEvent.objects.filter(event_type='twofa_locked', user=self.verified_user).exists())
