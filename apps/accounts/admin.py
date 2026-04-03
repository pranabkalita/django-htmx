from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from apps.accounts.models import BackgroundJob, EmailVerificationToken, PasswordResetToken, SecurityEvent, TwoFactorSettings, User
from apps.accounts.services.job_service import retry_background_job


# Restrict Django admin to superusers only.
def _superuser_admin_only(request):
    return bool(request.user and request.user.is_active and request.user.is_superuser)


admin.site.has_permission = _superuser_admin_only


class TwoFactorEnabledFilter(admin.SimpleListFilter):
    title = '2FA enabled'
    parameter_name = 'twofa_enabled'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Enabled'),
            ('0', 'Disabled'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == '1':
            return queryset.filter(twofa_settings__is_enabled=True)
        if value == '0':
            return queryset.exclude(twofa_settings__is_enabled=True)
        return queryset


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        'email',
        'full_name',
        'is_active',
        'is_email_verified',
        'twofa_enabled',
        'is_staff',
        'is_superuser',
        'date_joined',
    )
    list_filter = (
        'is_active',
        'is_email_verified',
        TwoFactorEnabledFilter,
        'is_staff',
        'is_superuser',
        'date_joined',
    )
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'is_email_verified')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('email', 'first_name', 'last_name', 'password1', 'password2', 'is_staff', 'is_superuser'),
            },
        ),
    )

    def full_name(self, obj):
        return obj.get_full_name() or '-'

    @admin.display(boolean=True, description='2FA enabled')
    def twofa_enabled(self, obj):
        twofa = getattr(obj, 'twofa_settings', None)
        return bool(twofa and twofa.is_enabled)

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        if not allowed:
            return False

        if obj is None:
            return True

        # Prevent deleting the currently logged-in superuser account.
        if request.user.is_authenticated and obj.pk == request.user.pk:
            return False

        # Prevent deleting the final remaining superuser account.
        if obj.is_superuser and not User.objects.filter(is_superuser=True).exclude(pk=obj.pk).exists():
            return False

        return True

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Disable bulk delete for User to avoid accidental admin lockout.
        actions.pop('delete_selected', None)
        return actions


@admin.register(TwoFactorSettings)
class TwoFactorSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_enabled')
    list_filter = ('is_enabled',)
    search_fields = ('user__email',)

    def get_readonly_fields(self, request, obj=None):
        # Secret is encrypted and should not be modified from admin.
        return ('secret',)

    def get_model_perms(self, request):
        # Keep this model out of the admin app/menu listing.
        return {}


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'user', 'ip_address', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('event_type', 'user__email', 'ip_address')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'expires_at', 'used_at')
    list_filter = ('expires_at', 'used_at')
    search_fields = ('user__email', 'token')
    ordering = ('-expires_at',)

    def has_add_permission(self, request):
        return False

    def get_model_perms(self, request):
        # Keep this model out of the admin app/menu listing.
        return {}


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'expires_at', 'used_at')
    list_filter = ('expires_at', 'used_at')
    search_fields = ('user__email', 'token')
    ordering = ('-expires_at',)

    def has_add_permission(self, request):
        return False

    def get_model_perms(self, request):
        # Keep this model out of the admin app/menu listing.
        return {}


@admin.register(BackgroundJob)
class BackgroundJobAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'task_name',
        'status',
        'queue_name',
        'execution_ms',
        'retries',
        'triggered_by',
        'created_at',
        'retry_now',
    )
    list_filter = ('status', 'queue_name', 'created_at')
    search_fields = ('task_id', 'task_name', 'failure_reason', 'triggered_by__email')
    ordering = ('-created_at',)
    readonly_fields = (
        'task_id',
        'task_name',
        'queue_name',
        'status',
        'retries',
        'payload',
        'result_text',
        'failure_reason',
        'started_at',
        'finished_at',
        'execution_ms',
        'last_retry_at',
        'triggered_by',
        'created_at',
        'updated_at',
    )
    actions = ('retry_failed_jobs', 'retry_pending_jobs')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/retry/',
                self.admin_site.admin_view(self.retry_single_job_view),
                name='accounts_backgroundjob_retry',
            ),
        ]
        return custom_urls + urls

    @admin.display(description='Retry')
    def retry_now(self, obj):
        if obj.status not in {BackgroundJob.STATUS_FAILED, BackgroundJob.STATUS_PENDING}:
            return '-'
        retry_url = reverse('admin:accounts_backgroundjob_retry', args=[obj.pk])
        return format_html('<a class="button" href="{}">Retry</a>', retry_url)

    def retry_single_job_view(self, request, object_id):
        job = get_object_or_404(BackgroundJob, pk=object_id)
        can_retry = job.status in {BackgroundJob.STATUS_FAILED, BackgroundJob.STATUS_PENDING}

        if request.method == 'POST':
            if not can_retry:
                self.message_user(
                    request,
                    f'Job #{job.id} cannot be retried from status "{job.status}".',
                    level=messages.WARNING,
                )
                return TemplateResponse(request, 'admin/accounts/backgroundjob/retry_confirmation.html', {
                    **self.admin_site.each_context(request),
                    'opts': self.model._meta,
                    'job': job,
                    'title': f'Retry Background Job #{job.id}',
                    'can_retry': False,
                })
            retry_background_job(job, triggered_by=request.user)
            self.message_user(request, f'Job #{job.id} retried successfully.', level=messages.SUCCESS)
            return HttpResponseRedirect(reverse('admin:accounts_backgroundjob_changelist'))

        return TemplateResponse(
            request,
            'admin/accounts/backgroundjob/retry_confirmation.html',
            {
                **self.admin_site.each_context(request),
                'opts': self.model._meta,
                'job': job,
                'title': f'Retry Background Job #{job.id}',
                'can_retry': can_retry,
            },
        )

    @admin.action(description='Retry selected FAILED jobs')
    def retry_failed_jobs(self, request, queryset):
        retried = 0
        for job in queryset.filter(status=BackgroundJob.STATUS_FAILED):
            retry_background_job(job, triggered_by=request.user)
            retried += 1
        if retried:
            self.message_user(request, f'Retried {retried} failed job(s).', level=messages.SUCCESS)
        else:
            self.message_user(request, 'No failed jobs selected.', level=messages.WARNING)

    @admin.action(description='Retry selected PENDING jobs')
    def retry_pending_jobs(self, request, queryset):
        retried = 0
        for job in queryset.filter(status=BackgroundJob.STATUS_PENDING):
            retry_background_job(job, triggered_by=request.user)
            retried += 1
        if retried:
            self.message_user(request, f'Retried {retried} pending job(s).', level=messages.SUCCESS)
        else:
            self.message_user(request, 'No pending jobs selected.', level=messages.WARNING)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
