import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger('mail_log')


def send_template_email(subject, body, recipients, html_template=None, context=None):
    if html_template:
        html_body = render_to_string(html_template, context or {})
        message = EmailMultiAlternatives(subject, body, settings.DEFAULT_FROM_EMAIL, recipients)
        message.attach_alternative(html_body, 'text/html')
        message.send(fail_silently=False)
    else:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)

    if settings.MAIL_DRIVER == 'log':
        logger.info('mail logged subject=%s recipients=%s', subject, ','.join(recipients))
