from apps.common.views.rendering import render_htmx


def landing(request):
    return render_htmx(request, 'pages/landing.html', 'pages/partials/landing_content.html', shell='guest')


def about(request):
    return render_htmx(request, 'pages/about.html', 'pages/partials/about_content.html', shell='guest')


def contact(request):
    return render_htmx(request, 'pages/contact.html', 'pages/partials/contact_content.html', shell='guest')
