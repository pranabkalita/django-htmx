from django.conf import settings
from django.db import models

from apps.accounts.models.base import AuditSoftDeleteModel


class SecurityEvent(AuditSoftDeleteModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['event_type', 'created_at'], name='accounts_se_event_time_idx'),
        ]

    def __str__(self):
        return f'{self.event_type}#{self.user_id or "anonymous"}'


class AuditActivity(AuditSoftDeleteModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=128, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['action', 'created_at'], name='accounts_audit_action_time_idx'),
            models.Index(fields=['entity_type', 'entity_id'], name='accounts_audit_entity_idx'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        target = f'{self.entity_type}:{self.entity_id}' if self.entity_type and self.entity_id else 'n/a'
        return f'{self.action} ({target})'
