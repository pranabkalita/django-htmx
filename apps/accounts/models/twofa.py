from django.conf import settings
from django.db import models
from apps.common.fields import EncryptedTextField


class TwoFactorSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='twofa_settings')
    secret = EncryptedTextField(blank=True)
    is_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f'2FA({self.user_id})'
