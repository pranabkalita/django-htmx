from django.conf import settings
from django.db import models

from apps.accounts.models.base import AuditSoftDeleteModel


class BackgroundJob(AuditSoftDeleteModel):
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_RETRIED = 'retried'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_RETRIED, 'Retried'),
    ]

    task_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    task_name = models.CharField(max_length=128)
    queue_name = models.CharField(max_length=64, default='celery')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    retries = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    result_text = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    execution_ms = models.PositiveIntegerField(null=True, blank=True)
    last_retry_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.task_name}#{self.task_id or self.id}'
