from datetime import timedelta

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, PasswordResetToken, User
from apps.accounts.services import session_service
from apps.accounts.services.auth_service import build_email_verification, build_password_reset


def create_session_for_user(user_id, *, expire_in_seconds=3600):
    session = SessionStore()
    session['_auth_user_id'] = str(user_id)
    session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
    session['_auth_user_hash'] = 'hash'
    session.set_expiry(expire_in_seconds)
    session.save()
    return session.session_key


class AuthServiceTokenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='svc@example.com',
            first_name='Svc',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )

    def test_build_email_verification_rotates_previous_active_tokens(self):
        old = EmailVerificationToken.objects.create(
            user=self.user,
            token='old-token',
            expires_at=timezone.now() + timedelta(hours=2),
        )

        new = build_email_verification(self.user)

        old.refresh_from_db()
        self.assertIsNotNone(old.used_at)
        self.assertNotEqual(old.token, new.token)
        self.assertTrue(new.used_at is None)

    def test_build_password_reset_rotates_previous_active_tokens(self):
        old = PasswordResetToken.objects.create(
            user=self.user,
            token='old-reset-token',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        new = build_password_reset(self.user)

        old.refresh_from_db()
        self.assertIsNotNone(old.used_at)
        self.assertNotEqual(old.token, new.token)
        self.assertTrue(new.used_at is None)


class SessionServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='session@example.com',
            first_name='Session',
            last_name='Owner',
            password='StrongPass123!',
            is_email_verified=True,
        )
        self.other = User.objects.create_user(
            email='other@example.com',
            first_name='Other',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )

    def test_get_user_sessions_only_returns_owned_and_current_first(self):
        current_key = create_session_for_user(self.user.id, expire_in_seconds=5000)
        older_key = create_session_for_user(self.user.id, expire_in_seconds=1000)
        create_session_for_user(self.other.id, expire_in_seconds=1000)

        sessions = session_service.get_user_sessions(self.user.id, current_key)

        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0]['session_key'], current_key)
        self.assertTrue(sessions[0]['is_current'])
        self.assertIn(older_key, [item['session_key'] for item in sessions])

    def test_revoke_session_requires_ownership(self):
        other_key = create_session_for_user(self.other.id)

        revoked = session_service.revoke_session(other_key, self.user.id)

        self.assertFalse(revoked)
        self.assertTrue(Session.objects.filter(session_key=other_key).exists())

    def test_revoke_all_sessions_respects_except_key(self):
        keep_key = create_session_for_user(self.user.id)
        drop_key = create_session_for_user(self.user.id)

        removed_count = session_service.revoke_all_sessions(self.user.id, except_key=keep_key)

        self.assertEqual(removed_count, 1)
        self.assertTrue(Session.objects.filter(session_key=keep_key).exists())
        self.assertFalse(Session.objects.filter(session_key=drop_key).exists())
