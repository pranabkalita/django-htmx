from time import perf_counter

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import BackgroundJob
from apps.accounts.services.audit_log_service import log_activity


EMAIL_TASK_NAME = 'apps.accounts.tasks.email_tasks.send_email_task'


def enqueue_email_job(*, subject, body, recipients, html_template=None, context=None, triggered_by=None):
    # Store only non-sensitive metadata in the DB record. The full message
    # content (body, context with token URLs, recipient addresses) is passed
    # directly to the Celery task and kept only in the broker's ephemeral store.
    db_payload = {
        'subject': subject,
        'recipient_count': len(recipients) if recipients else 0,
        'template': html_template,
    }
    task_payload = {
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
            payload=db_payload,
            triggered_by=triggered_by,
            created_by=triggered_by,
        )

        from apps.accounts.tasks.email_tasks import send_email_task

        async_result = send_email_task.delay(job_id=job.id, **task_payload)
        job.task_id = async_result.id
        job.save(update_fields=['task_id', 'updated_at'])

    log_activity(
        action='background_job_created',
        actor=triggered_by,
        entity=job,
        metadata={'task_name': job.task_name, 'queue_name': job.queue_name},
    )

    return job


def _job_update_queryset(*, task_id=None, job_id=None):
    if job_id:
        return BackgroundJob.objects.filter(id=job_id)
    if task_id:
        return BackgroundJob.objects.filter(task_id=task_id)
    return BackgroundJob.objects.none()


def mark_job_running(task_id=None, *, job_id=None):
    qs = _job_update_queryset(task_id=task_id, job_id=job_id)
    if not qs.exists():
        return
    qs.update(
        status=BackgroundJob.STATUS_RUNNING,
        started_at=timezone.now(),
        failure_reason='',
    )
    updated = qs.first()
    if updated:
        log_activity(action='background_job_running', actor=updated.triggered_by, entity=updated)


def mark_job_success(task_id=None, *, started_monotonic, job_id=None):
    qs = _job_update_queryset(task_id=task_id, job_id=job_id)
    if not qs.exists():
        return
    execution_ms = max(1, int((perf_counter() - started_monotonic) * 1000))
    qs.update(
        status=BackgroundJob.STATUS_SUCCESS,
        finished_at=timezone.now(),
        execution_ms=execution_ms,
        result_text='Completed',
        failure_reason='',
    )
    updated = qs.first()
    if updated:
        log_activity(action='background_job_succeeded', actor=updated.triggered_by, entity=updated)


def mark_job_failure(task_id=None, *, reason, job_id=None):
    qs = _job_update_queryset(task_id=task_id, job_id=job_id)
    if not qs.exists():
        return
    qs.update(
        status=BackgroundJob.STATUS_FAILED,
        finished_at=timezone.now(),
        failure_reason=(reason or '')[:2000],
    )
    updated = qs.first()
    if updated:
        log_activity(
            action='background_job_failed',
            actor=updated.triggered_by,
            entity=updated,
            metadata={'reason': (reason or '')[:2000]},
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

    log_activity(
        action='background_job_retried',
        actor=triggered_by,
        entity=job,
        metadata={'retried_as_job_id': retried_job.id},
    )

    return retried_job
