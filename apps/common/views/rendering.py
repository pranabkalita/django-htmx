import re
import json
from urllib.parse import urlsplit

from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import Resolver404
from django.urls import resolve


CONTENT_PATTERN = re.compile(
    r'<(?:main|section)\b[^>]*\bid=["\']content["\'][^>]*>(?P<content>.*)</(?:main|section)>',
    re.DOTALL,
)
BODY_PATTERN = re.compile(r'<body\b[^>]*>(?P<body>.*)</body>', re.DOTALL)


def _extract_body_content(rendered_html):
    match = BODY_PATTERN.search(rendered_html)
    if match:
        return match.group('body').strip()
    return rendered_html


def _path_from_url(value):
    if not value:
        return ''
    return urlsplit(value).path or value


def _shell_from_view(view_callable):
    explicit_shell = getattr(view_callable, 'route_shell', None)
    if explicit_shell in {'guest', 'auth'}:
        return explicit_shell

    # django.contrib.auth.decorators.login_required wraps callables and exposes login_url.
    if getattr(view_callable, 'login_url', None) is not None:
        return 'auth'

    view_class = getattr(view_callable, 'view_class', None)
    if view_class:
        explicit_shell = getattr(view_class, 'route_shell', None)
        if explicit_shell in {'guest', 'auth'}:
            return explicit_shell
        if getattr(view_class, 'login_url', None) is not None:
            return 'auth'

    return 'guest'


def _shell_for_path(path, fallback='guest'):
    path = _path_from_url(path)
    if not path:
        return fallback

    try:
        match = resolve(path)
    except Resolver404:
        return fallback

    return _shell_from_view(match.func)


def _current_shell(request):
    current_url = request.headers.get('HX-Current-URL')
    path = _path_from_url(current_url) or request.path
    return _shell_for_path(path)


def _target_shell(request, explicit_shell):
    if explicit_shell in {'guest', 'auth'}:
        return explicit_shell
    return _shell_for_path(request.path)


def _shell_swap_required(request, shell):
    return request.headers.get('HX-Request') == 'true' and shell and _current_shell(request) != shell


def _extract_htmx_content(rendered_html):
    match = CONTENT_PATTERN.search(rendered_html)
    if match:
        return match.group('content').strip()
    return rendered_html


def render_htmx(request, full_template, partial_template, context=None, status=200, shell=None):
    context = context or {}
    target_shell = _target_shell(request, shell)
    if request.headers.get('HX-Request') == 'true':
        rendered_html = render_to_string(full_template, context=context, request=request)
        response = HttpResponse(_extract_htmx_content(rendered_html), status=status)
        if _shell_swap_required(request, target_shell):
            response = HttpResponse(_extract_body_content(rendered_html), status=status)
            response['HX-Retarget'] = 'body'
            response['HX-Reswap'] = 'innerHTML'
        return response
    return render(request, full_template, context, status=status)


def htmx_redirect(request, to, shell=None):
    target_shell = _shell_for_path(to, fallback=shell or 'guest')
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse(status=204)
        if _shell_swap_required(request, target_shell):
            response['HX-Location'] = json.dumps({'path': to, 'target': 'body', 'swap': 'innerHTML'})
        else:
            response['HX-Location'] = to
        return response
    return redirect(to)
