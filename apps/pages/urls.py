from django.urls import path
from apps.pages.views import public

app_name = 'pages'

urlpatterns = [
    path('', public.landing, name='landing'),
    path('about/', public.about, name='about'),
    path('contact/', public.contact, name='contact'),
]
