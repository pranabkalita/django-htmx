from django.test import TestCase
from django.urls import reverse


class MiddlewareBehaviorTests(TestCase):
    def test_request_id_header_is_added(self):
        response = self.client.get(reverse('pages:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.headers.get('X-Request-ID'))

    def test_security_headers_are_added(self):
        response = self.client.get(reverse('pages:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(response.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')
        self.assertEqual(response.headers.get('Permissions-Policy'), 'camera=(), microphone=(), geolocation=()')
        csp = response.headers.get('Content-Security-Policy', '')
        self.assertIn("default-src 'self'", csp)
        self.assertIn("style-src 'self'", csp)
        self.assertNotIn('unsafe-inline', csp)
