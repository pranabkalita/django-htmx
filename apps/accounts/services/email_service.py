import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger('mail_log')


def send_template_email(subject, body, recipients):
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    if settings.MAIL_DRIVER == 'log':
        logger.info('mail logged subject=%s recipients=%s', subject, ','.join(recipients))
