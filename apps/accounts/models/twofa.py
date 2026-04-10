from django.conf import settings
from django.db import models
from apps.common.fields import EncryptedTextField

from apps.accounts.models.base import AuditSoftDeleteModel


class TwoFactorSettings(AuditSoftDeleteModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='twofa_settings')
    secret = EncryptedTextField(blank=True)
    is_enabled = models.BooleanField(default=False)
    last_otp_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'2FA({self.user_id})'
