from django.conf import settings
from django.db import models


class TwoFactorSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='twofa_settings')
    secret = models.CharField(max_length=64, blank=True)
    is_enabled = models.BooleanField(default=False)
