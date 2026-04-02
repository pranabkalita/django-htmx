from django.urls import path

from apps.accounts.views import auth_private, auth_public

app_name = 'accounts'

urlpatterns = [
    path('login/', auth_public.login_view, name='login'),
    path('register/', auth_public.register, name='register'),
    path('verify-email/<str:token>/', auth_public.verify_email, name='verify_email'),
    path('forgot-password/', auth_public.forgot_password, name='forgot_password'),
    path('resend-verification/', auth_public.resend_verification, name='resend_verification'),
    path('reset-password/<str:token>/', auth_public.reset_password, name='reset_password'),
    path('2fa-challenge/', auth_public.twofa_challenge, name='twofa_challenge'),
    path('logout/', auth_private.logout_view, name='logout'),
    path('dashboard/', auth_private.dashboard, name='dashboard'),
    path('profile/', auth_private.profile, name='profile'),
    path('change-password/', auth_private.change_password, name='change_password'),
    path('2fa/', auth_private.twofa_settings, name='twofa_settings'),
    path('sessions/', auth_private.sessions_list, name='sessions'),
    path('sessions/revoke/', auth_private.revoke_session_view, name='revoke_session'),
    path('sessions/revoke-all/', auth_private.revoke_all_sessions_view, name='revoke_all_sessions'),
    path('deactivate/', auth_private.deactivate_account, name='deactivate_account'),
]
