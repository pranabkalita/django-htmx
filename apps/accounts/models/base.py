from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)

    def with_deleted(self):
        return self.all()

    def soft_delete(self, *, deleted_by=None, deleted_at=None):
        deleted_at = deleted_at or timezone.now()
        updates = {
            'is_deleted': True,
            'deleted_at': deleted_at,
        }
        if hasattr(self.model, 'deleted_by_id'):
            updates['deleted_by'] = deleted_by
        return self.filter(is_deleted=False).update(**updates)

    def restore(self):
        updates = {
            'is_deleted': False,
            'deleted_at': None,
        }
        if hasattr(self.model, 'deleted_by_id'):
            updates['deleted_by'] = None
        return self.update(**updates)

    def hard_delete(self):
        return super().delete()

    def delete(self):
        return self.soft_delete()


class ActiveSoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    pass


class AuditSoftDeleteModel(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_created',
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_deleted',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveSoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def soft_delete(self, *, deleted_by=None, deleted_at=None, update_fields=None):
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = deleted_at or timezone.now()
        self.deleted_by = deleted_by
        fields = ['is_deleted', 'deleted_at', 'deleted_by', 'updated_at']
        if update_fields:
            fields.extend(update_fields)
        self.save(update_fields=fields)

    def restore(self):
        if not self.is_deleted:
            return
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'updated_at'])

    def hard_delete(self):
        return super().delete()

    def delete(self, using=None, keep_parents=False):
        self.soft_delete()
