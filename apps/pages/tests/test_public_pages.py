from django.test import TestCase
from django.urls import reverse


class PublicPageViewTests(TestCase):
    def test_landing_loads_guest_shell(self):
        response = self.client.get(reverse('pages:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Secure Identity Platform')

    def test_about_page_loads(self):
        response = self.client.get(reverse('pages:about'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'About Us')

    def test_contact_page_loads(self):
        response = self.client.get(reverse('pages:contact'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Contact Us')

    def test_htmx_about_swaps_content_only_in_guest_shell(self):
        response = self.client.get(
            reverse('pages:about'),
            HTTP_HX_REQUEST='true',
            HTTP_HX_CURRENT_URL='http://testserver/',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'About Us')
        self.assertIsNone(response.headers.get('HX-Retarget'))
        self.assertIsNone(response.headers.get('HX-Reswap'))
