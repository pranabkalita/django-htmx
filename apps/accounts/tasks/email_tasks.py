from celery import shared_task

from apps.accounts.services.email_service import send_template_email


@shared_task
def send_email_task(subject, body, recipients, html_template=None, context=None):
    send_template_email(subject, body, recipients, html_template=html_template, context=context)
