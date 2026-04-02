import re

from django.http import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.template.loader import render_to_string


CONTENT_PATTERN = re.compile(
    r'<(?:main|section)\b[^>]*\bid=["\']content["\'][^>]*>(?P<content>.*)</(?:main|section)>',
    re.DOTALL,
)


def _extract_htmx_content(rendered_html):
    match = CONTENT_PATTERN.search(rendered_html)
    if match:
        return match.group('content').strip()
    return rendered_html


def render_htmx(request, full_template, partial_template, context=None, status=200):
    context = context or {}
    if request.headers.get('HX-Request') == 'true':
        rendered_html = render_to_string(full_template, context=context, request=request)
        return HttpResponse(_extract_htmx_content(rendered_html), status=status)
    return render(request, full_template, context, status=status)


def htmx_redirect(request, to):
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse(status=204)
        response["HX-Location"] = to
        return response
    return redirect(to)
