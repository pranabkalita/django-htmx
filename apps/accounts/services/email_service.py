from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail import send_mail
from django.template.loader import render_to_string


def send_template_email(subject, body, recipients, html_template=None, context=None):
    context = {
        'app_name': settings.APP_NAME,
        **(context or {}),
    }
    from_email = settings.FORMATTED_FROM_EMAIL
    if html_template:
        html_body = render_to_string(html_template, context)
        message = EmailMultiAlternatives(subject, body, from_email, recipients)
        message.attach_alternative(html_body, 'text/html')
        message.send(fail_silently=False)
    else:
        send_mail(subject, body, from_email, recipients, fail_silently=False)
