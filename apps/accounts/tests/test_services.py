from datetime import timedelta
from time import perf_counter
from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import AuditActivity, BackgroundJob, EmailVerificationToken, PasswordResetToken, SecurityEvent, User
from apps.accounts.services import job_service, session_service
from apps.accounts.services.auth_service import (
    authenticate_user,
    build_email_verification,
    build_password_reset,
    clear_login_failures,
    get_login_lock_seconds,
    purge_expired_auth_tokens,
    register_login_failure,
    record_security_event,
)
from apps.accounts.services.user_service import deactivate_user


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
        self.assertNotEqual(new.token, new.raw_token)
        self.assertEqual(len(new.token), 64)
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
        self.assertNotEqual(new.token, new.raw_token)
        self.assertEqual(len(new.token), 64)
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


class AuthServiceAuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='service-user@example.com',
            first_name='Service',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )

    def test_authenticate_user_accepts_mixed_case_email(self):
        user = authenticate_user('Service-User@Example.com', 'StrongPass123!')
        self.assertIsNotNone(user)
        self.assertEqual(user.id, self.user.id)

    def test_authenticate_user_trims_email_whitespace(self):
        user = authenticate_user('  service-user@example.com  ', 'StrongPass123!')
        self.assertIsNotNone(user)
        self.assertEqual(user.id, self.user.id)


class JobServiceStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='job-service@example.com',
            first_name='Job',
            last_name='Service',
            password='StrongPass123!',
            is_email_verified=True,
        )

    @patch('apps.accounts.tasks.email_tasks.send_email_task.delay')
    def test_enqueue_email_job_passes_job_id_to_task(self, mock_delay):
        class _Result:
            id = 'task-id-123'

        mock_delay.return_value = _Result()

        job = job_service.enqueue_email_job(
            subject='Subject',
            body='Body',
            recipients=['job@example.com'],
            triggered_by=self.user,
        )

        self.assertEqual(job.task_id, 'task-id-123')
        self.assertEqual(mock_delay.call_count, 1)
        self.assertEqual(mock_delay.call_args.kwargs['job_id'], job.id)

    def test_mark_job_running_updates_by_job_id_when_task_id_missing(self):
        job = BackgroundJob.objects.create(
            task_name=job_service.EMAIL_TASK_NAME,
            queue_name='celery',
            status=BackgroundJob.STATUS_PENDING,
            payload={'subject': 's', 'body': 'b', 'recipients': ['x@example.com']},
        )

        job_service.mark_job_running(job_id=job.id)
        job.refresh_from_db()

        self.assertEqual(job.status, BackgroundJob.STATUS_RUNNING)
        self.assertIsNotNone(job.started_at)

    def test_mark_job_success_still_updates_by_task_id(self):
        job = BackgroundJob.objects.create(
            task_id='task-id-success',
            task_name=job_service.EMAIL_TASK_NAME,
            queue_name='celery',
            status=BackgroundJob.STATUS_RUNNING,
            payload={'subject': 's', 'body': 'b', 'recipients': ['x@example.com']},
        )

        started = perf_counter()
        job_service.mark_job_success('task-id-success', started_monotonic=started)
        job.refresh_from_db()

        self.assertEqual(job.status, BackgroundJob.STATUS_SUCCESS)
        self.assertEqual(job.result_text, 'Completed')

    def test_mark_job_failure_prefers_job_id_over_task_id(self):
        target = BackgroundJob.objects.create(
            task_id='task-target',
            task_name=job_service.EMAIL_TASK_NAME,
            queue_name='celery',
            status=BackgroundJob.STATUS_RUNNING,
            payload={'subject': 's', 'body': 'b', 'recipients': ['x@example.com']},
        )
        other = BackgroundJob.objects.create(
            task_id='task-other',
            task_name=job_service.EMAIL_TASK_NAME,
            queue_name='celery',
            status=BackgroundJob.STATUS_RUNNING,
            payload={'subject': 's', 'body': 'b', 'recipients': ['x@example.com']},
        )

        job_service.mark_job_failure('task-target', reason='boom', job_id=other.id)
        target.refresh_from_db()
        other.refresh_from_db()

        self.assertEqual(target.status, BackgroundJob.STATUS_RUNNING)
        self.assertEqual(other.status, BackgroundJob.STATUS_FAILED)
        self.assertEqual(other.failure_reason, 'boom')


class LoginLockoutServiceTests(TestCase):
    @override_settings(
        LOGIN_FAILURE_THRESHOLD=2,
        LOGIN_FAILURE_BASE_LOCK_SECONDS=60,
        LOGIN_FAILURE_MAX_LOCK_SECONDS=60,
        LOGIN_FAILURE_WINDOW_SECONDS=300,
    )
    def test_register_login_failure_sets_lock_after_threshold(self):
        email = 'lock@example.com'
        clear_login_failures(email)

        self.assertEqual(register_login_failure(email), 0)
        self.assertEqual(register_login_failure(email), 60)
        self.assertGreater(get_login_lock_seconds(email), 0)

    @override_settings(
        LOGIN_FAILURE_THRESHOLD=2,
        LOGIN_FAILURE_BASE_LOCK_SECONDS=60,
        LOGIN_FAILURE_MAX_LOCK_SECONDS=60,
        LOGIN_FAILURE_WINDOW_SECONDS=300,
    )
    def test_clear_login_failures_removes_lock(self):
        email = 'lock-clear@example.com'
        clear_login_failures(email)
        register_login_failure(email)
        register_login_failure(email)

        clear_login_failures(email)
        self.assertEqual(get_login_lock_seconds(email), 0)


class AuthTokenCleanupServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='cleanup@example.com',
            first_name='Cleanup',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )

    def test_purge_expired_auth_tokens_removes_expired_and_used(self):
        EmailVerificationToken.objects.create(
            user=self.user,
            token='a' * 64,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        PasswordResetToken.objects.create(
            user=self.user,
            token='b' * 64,
            expires_at=timezone.now() + timedelta(hours=1),
            used_at=timezone.now(),
        )

        summary = purge_expired_auth_tokens()

        self.assertGreaterEqual(summary['email_verification_deleted'], 1)
        self.assertGreaterEqual(summary['password_reset_deleted'], 1)
        self.assertEqual(EmailVerificationToken.objects.count(), 0)
        self.assertEqual(PasswordResetToken.objects.count(), 0)


class AuditAndSoftDeleteServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='audit-soft-delete@example.com',
            first_name='Audit',
            last_name='Subject',
            password='StrongPass123!',
            is_email_verified=True,
        )

    def test_soft_deleted_tokens_are_hidden_by_default_and_restorable(self):
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token='c' * 64,
            expires_at=timezone.now() + timedelta(hours=2),
            created_by=self.user,
        )
        token.soft_delete(deleted_by=self.user)

        self.assertFalse(EmailVerificationToken.objects.filter(id=token.id).exists())
        self.assertTrue(EmailVerificationToken.all_objects.filter(id=token.id, is_deleted=True).exists())

        token.refresh_from_db(from_queryset=EmailVerificationToken.all_objects)
        token.restore()
        self.assertTrue(EmailVerificationToken.objects.filter(id=token.id, is_deleted=False).exists())

    def test_record_security_event_writes_central_audit_activity(self):
        record_security_event(event_type='login_success', user=self.user, ip_address='203.0.113.4')

        self.assertTrue(SecurityEvent.objects.filter(user=self.user, event_type='login_success').exists())
        self.assertTrue(
            AuditActivity.objects.filter(
                actor=self.user,
                action='login_success',
                metadata__source='security_event',
            ).exists()
        )

    def test_deactivate_user_soft_deletes_and_logs_activity(self):
        deactivate_user(self.user, actor=self.user)
        self.user.refresh_from_db(from_queryset=User.objects.with_deleted())

        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.is_deleted)
        self.assertIsNotNone(self.user.deleted_at)
        self.assertEqual(self.user.deleted_by_id, self.user.id)
        self.assertTrue(AuditActivity.objects.filter(action='user_deactivated', actor=self.user).exists())
