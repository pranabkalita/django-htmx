from django.conf import settings
from django.db import models


class SecurityEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.event_type}#{self.user_id or "anonymous"}'
