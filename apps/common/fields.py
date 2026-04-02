from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from cryptography.fernet import Fernet, InvalidToken


class EncryptedTextField(models.TextField):
    """Stores encrypted text at rest while presenting plaintext in Python."""

    @staticmethod
    def _fernet():
        key = getattr(settings, 'FERNET_KEY', '')
        if not key:
            raise ImproperlyConfigured('FERNET_KEY must be set for EncryptedTextField.')
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ''):
            return value
        encrypted = self._fernet().encrypt(str(value).encode())
        return encrypted.decode()

    def from_db_value(self, value, expression, connection):
        if value in (None, ''):
            return value
        try:
            return self._fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            # Backward compatibility for legacy plaintext rows.
            return value

    def to_python(self, value):
        if value in (None, '') or not isinstance(value, str):
            return value
        try:
            return self._fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            return value
