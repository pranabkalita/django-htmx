from time import perf_counter

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import BackgroundJob


EMAIL_TASK_NAME = 'apps.accounts.tasks.email_tasks.send_email_task'


def enqueue_email_job(*, subject, body, recipients, html_template=None, context=None, triggered_by=None):
    payload = {
        'subject': subject,
        'body': body,
        'recipients': recipients,
        'html_template': html_template,
        'context': context or {},
    }

    with transaction.atomic():
        job = BackgroundJob.objects.create(
            task_name=EMAIL_TASK_NAME,
            queue_name='celery',
            status=BackgroundJob.STATUS_PENDING,
            payload=payload,
            triggered_by=triggered_by,
        )

        from apps.accounts.tasks.email_tasks import send_email_task

        async_result = send_email_task.delay(**payload)
        job.task_id = async_result.id
        job.save(update_fields=['task_id', 'updated_at'])

    return job


def mark_job_running(task_id):
    if not task_id:
        return
    BackgroundJob.objects.filter(task_id=task_id).update(
        status=BackgroundJob.STATUS_RUNNING,
        started_at=timezone.now(),
        failure_reason='',
    )


def mark_job_success(task_id, *, started_monotonic):
    if not task_id:
        return
    execution_ms = max(1, int((perf_counter() - started_monotonic) * 1000))
    BackgroundJob.objects.filter(task_id=task_id).update(
        status=BackgroundJob.STATUS_SUCCESS,
        finished_at=timezone.now(),
        execution_ms=execution_ms,
        result_text='Completed',
        failure_reason='',
    )


def mark_job_failure(task_id, *, reason):
    if not task_id:
        return
    BackgroundJob.objects.filter(task_id=task_id).update(
        status=BackgroundJob.STATUS_FAILED,
        finished_at=timezone.now(),
        failure_reason=(reason or '')[:2000],
    )


def retry_background_job(job, *, triggered_by=None):
    payload = job.payload or {}
    if job.task_name != EMAIL_TASK_NAME:
        raise ValueError('Unsupported job type for retry.')

    retried_job = enqueue_email_job(
        subject=payload.get('subject', ''),
        body=payload.get('body', ''),
        recipients=payload.get('recipients', []),
        html_template=payload.get('html_template'),
        context=payload.get('context') or {},
        triggered_by=triggered_by,
    )

    job.status = BackgroundJob.STATUS_RETRIED
    job.last_retry_at = timezone.now()
    job.retries = job.retries + 1
    job.result_text = f'Retried as job #{retried_job.id}'
    job.save(update_fields=['status', 'last_retry_at', 'retries', 'result_text', 'updated_at'])

    return retried_job
