from django.test import TestCase
from django.urls import reverse

import pyotp

from apps.accounts.models import User
from apps.accounts.services.twofa_service import get_or_create_twofa


class AuthSmokeTests(TestCase):
    def test_register_page_loads(self):
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)

    def test_unverified_user_cannot_login(self):
        User.objects.create_user(
            email='u@example.com',
            first_name='U',
            last_name='T',
            password='StrongPass123!',
            is_email_verified=False,
        )
        response = self.client.post(
            reverse('accounts:login'),
            {'email': 'u@example.com', 'password': 'StrongPass123!', 'remember_me': False},
            follow=True,
        )
        self.assertContains(response, 'Please verify your email before login.')

    def test_htmx_register_redirects_with_hx_location(self):
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
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get('HX-Location'), reverse('accounts:login'))

    def test_htmx_login_redirects_with_hx_location(self):
        User.objects.create_user(
            email='verified@example.com',
            first_name='Verified',
            last_name='User',
            password='StrongPass123!',
            is_email_verified=True,
        )
        response = self.client.post(
            reverse('accounts:login'),
            {'email': 'verified@example.com', 'password': 'StrongPass123!', 'remember_me': True},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get('HX-Location'), reverse('accounts:dashboard'))

    def test_htmx_change_password_redirects_with_hx_location(self):
        user = User.objects.create_user(
            email='cp@example.com',
            first_name='Change',
            last_name='Password',
            password='OldPass123!',
            is_email_verified=True,
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse('accounts:change_password'),
            {
                'old_password': 'OldPass123!',
                'new_password1': 'NewPass123!@',
                'new_password2': 'NewPass123!@',
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get('HX-Location'), reverse('accounts:login'))

    def test_htmx_twofa_challenge_redirects_with_hx_location(self):
        user = User.objects.create_user(
            email='twofa@example.com',
            first_name='Two',
            last_name='FA',
            password='StrongPass123!',
            is_email_verified=True,
        )
        twofa = get_or_create_twofa(user)
        twofa.secret = pyotp.random_base32()
        twofa.is_enabled = True
        twofa.save(update_fields=['secret', 'is_enabled'])

        session = self.client.session
        session['pre_2fa_user_id'] = user.id
        session.save()

        otp = pyotp.TOTP(twofa.secret).now()
        response = self.client.post(
            reverse('accounts:twofa_challenge'),
            {'otp_code': otp},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get('HX-Location'), reverse('accounts:dashboard'))
