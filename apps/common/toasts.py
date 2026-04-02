from django.contrib import messages


VALID_LEVELS = {'success', 'error', 'warning', 'info'}
VALID_POSITIONS = {
    'top-right',
    'top-center',
    'top-left',
    'bottom-right',
    'bottom-center',
    'bottom-left',
}

DEFAULT_POSITION = 'top-right'
DEFAULT_DURATION_MS = {
    'success': 3500,
    'info': 3500,
    'warning': 5000,
    'error': 6500,
}


def add_toast(request, text, *, level='info', position=DEFAULT_POSITION, duration_ms=None):
    level = level if level in VALID_LEVELS else 'info'
    position = position if position in VALID_POSITIONS else DEFAULT_POSITION
    duration_ms = int(duration_ms or DEFAULT_DURATION_MS[level])

    extra_tags = f'toast toast-level-{level} toast-pos-{position} toast-dur-{duration_ms}'
    messages.add_message(request, _django_level(level), text, extra_tags=extra_tags)


def success(request, text, *, position=DEFAULT_POSITION, duration_ms=None):
    add_toast(request, text, level='success', position=position, duration_ms=duration_ms)


def error(request, text, *, position=DEFAULT_POSITION, duration_ms=None):
    add_toast(request, text, level='error', position=position, duration_ms=duration_ms)


def warning(request, text, *, position=DEFAULT_POSITION, duration_ms=None):
    add_toast(request, text, level='warning', position=position, duration_ms=duration_ms)


def info(request, text, *, position=DEFAULT_POSITION, duration_ms=None):
    add_toast(request, text, level='info', position=position, duration_ms=duration_ms)


def _django_level(level):
    if level == 'success':
        return messages.SUCCESS
    if level == 'error':
        return messages.ERROR
    if level == 'warning':
        return messages.WARNING
    return messages.INFO
