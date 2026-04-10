from time import perf_counter

from celery import shared_task

from apps.accounts.services.email_service import send_template_email
from apps.accounts.services.job_service import mark_job_failure, mark_job_running, mark_job_success


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, retry_kwargs={'max_retries': 3})
def send_email_task(self, subject, body, recipients, html_template=None, context=None, job_id=None):
    task_id = getattr(self.request, 'id', None)
    started = perf_counter()
    mark_job_running(task_id, job_id=job_id)
    try:
        send_template_email(subject, body, recipients, html_template=html_template, context=context)
    except Exception as exc:
        mark_job_failure(task_id, reason=str(exc), job_id=job_id)
        raise
    mark_job_success(task_id, started_monotonic=started, job_id=job_id)
