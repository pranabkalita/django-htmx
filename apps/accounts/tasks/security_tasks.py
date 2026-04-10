from celery import shared_task

from apps.accounts.services.auth_service import purge_expired_auth_tokens


@shared_task(bind=True)
def cleanup_expired_auth_tokens_task(self):
    return purge_expired_auth_tokens()
