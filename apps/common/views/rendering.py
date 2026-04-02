from django.shortcuts import render
from django.http import HttpResponse
from django.shortcuts import redirect


def render_htmx(request, full_template, partial_template, context=None, status=200):
    template_name = partial_template if request.headers.get('HX-Request') == 'true' else full_template
    return render(request, template_name, context or {}, status=status)


def htmx_redirect(request, to):
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse(status=204)
        response["HX-Location"] = to
        return response
    return redirect(to)
