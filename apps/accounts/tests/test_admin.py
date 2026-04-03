from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import BackgroundJob, User


class AdminAccessTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email='admin@example.com',
            first_name='Admin',
            last_name='Root',
            password='StrongPass123!',
        )
        self.staff = User.objects.create_user(
            email='staff@example.com',
            first_name='Staff',
            last_name='User',
            password='StrongPass123!',
            is_staff=True,
            is_email_verified=True,
        )

    def test_superuser_can_access_admin_index(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)

    def test_staff_non_superuser_cannot_access_admin_index(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_superuser_can_access_user_changelist(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:accounts_user_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'is_email_verified')


class BackgroundJobAdminActionTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email='admin2@example.com',
            first_name='Admin',
            last_name='Root',
            password='StrongPass123!',
        )
        self.client.force_login(self.superuser)

    @patch('apps.accounts.admin.retry_background_job')
    def test_retry_failed_action_retries_only_failed_jobs(self, mock_retry):
        failed = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_FAILED,
            payload={'subject': 'x', 'body': 'y', 'recipients': ['a@example.com']},
        )
        BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_SUCCESS,
            payload={'subject': 'x', 'body': 'y', 'recipients': ['a@example.com']},
        )

        self.client.post(
            reverse('admin:accounts_backgroundjob_changelist'),
            {
                'action': 'retry_failed_jobs',
                '_selected_action': [str(failed.id)],
            },
            follow=True,
        )

        mock_retry.assert_called_once()

    @patch('apps.accounts.admin.retry_background_job')
    def test_retry_pending_action_retries_only_pending_jobs(self, mock_retry):
        pending = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_PENDING,
            payload={'subject': 'x', 'body': 'y', 'recipients': ['a@example.com']},
        )

        self.client.post(
            reverse('admin:accounts_backgroundjob_changelist'),
            {
                'action': 'retry_pending_jobs',
                '_selected_action': [str(pending.id)],
            },
            follow=True,
        )

        mock_retry.assert_called_once()

    def test_retry_link_visibility_by_status(self):
        failed = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_FAILED,
            payload={},
        )
        pending = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_PENDING,
            payload={},
        )
        success = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_SUCCESS,
            payload={},
        )

        background_job_admin = admin.site._registry[BackgroundJob]

        self.assertIn('Retry', background_job_admin.retry_now(failed))
        self.assertIn('Retry', background_job_admin.retry_now(pending))
        self.assertEqual(background_job_admin.retry_now(success), '-')

    def test_retry_single_job_confirmation_page_loads(self):
        failed = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_FAILED,
            payload={},
        )

        response = self.client.get(reverse('admin:accounts_backgroundjob_retry', args=[failed.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirm Retry')

    @patch('apps.accounts.admin.retry_background_job')
    def test_retry_single_job_post_retries_when_eligible(self, mock_retry):
        failed = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_FAILED,
            payload={'subject': 'x', 'body': 'y', 'recipients': ['a@example.com']},
        )

        response = self.client.post(reverse('admin:accounts_backgroundjob_retry', args=[failed.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        mock_retry.assert_called_once_with(failed, triggered_by=self.superuser)

    @patch('apps.accounts.admin.retry_background_job')
    def test_retry_single_job_post_blocks_non_retryable_status(self, mock_retry):
        success = BackgroundJob.objects.create(
            task_name='apps.accounts.tasks.email_tasks.send_email_task',
            status=BackgroundJob.STATUS_SUCCESS,
            payload={},
        )

        response = self.client.post(reverse('admin:accounts_backgroundjob_retry', args=[success.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not eligible for retry')
        mock_retry.assert_not_called()


class UserAdminDeletionSafetyTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.primary_superuser = User.objects.create_superuser(
            email='root1@example.com',
            first_name='Root',
            last_name='One',
            password='StrongPass123!',
        )
        self.secondary_superuser = User.objects.create_superuser(
            email='root2@example.com',
            first_name='Root',
            last_name='Two',
            password='StrongPass123!',
        )
        self.regular_user = User.objects.create_user(
            email='member@example.com',
            first_name='Member',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )

    def test_superuser_cannot_delete_self_from_admin(self):
        self.client.force_login(self.primary_superuser)
        response = self.client.get(reverse('admin:accounts_user_delete', args=[self.primary_superuser.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(id=self.primary_superuser.id).exists())

    def test_superuser_can_delete_another_superuser_when_one_will_remain(self):
        self.client.force_login(self.primary_superuser)
        response = self.client.post(
            reverse('admin:accounts_user_delete', args=[self.secondary_superuser.id]),
            {'post': 'yes'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(id=self.secondary_superuser.id).exists())
        self.assertTrue(User.objects.filter(id=self.primary_superuser.id).exists())

    def test_superuser_can_delete_regular_user(self):
        self.client.force_login(self.primary_superuser)
        response = self.client.post(
            reverse('admin:accounts_user_delete', args=[self.regular_user.id]),
            {'post': 'yes'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(id=self.regular_user.id).exists())

    def test_bulk_delete_action_is_removed_for_user_admin(self):
        request = self.factory.get(reverse('admin:accounts_user_changelist'))
        request.user = self.primary_superuser
        user_admin = admin.site._registry[User]
        actions = user_admin.get_actions(request)
        self.assertNotIn('delete_selected', actions)

