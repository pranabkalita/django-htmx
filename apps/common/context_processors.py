from django.conf import settings


def app_meta(_request):
    return {'app_name': settings.APP_NAME}
