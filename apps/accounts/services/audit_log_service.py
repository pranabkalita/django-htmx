from apps.accounts.models import AuditActivity


def _entity_ref(entity=None, *, entity_type=None, entity_id=None):
    if entity is not None:
        return entity._meta.label_lower, str(entity.pk)
    return (entity_type or ''), (str(entity_id) if entity_id is not None else '')


def log_activity(*, action, actor=None, entity=None, entity_type=None, entity_id=None, ip_address=None, changes=None, metadata=None):
    resolved_type, resolved_id = _entity_ref(entity, entity_type=entity_type, entity_id=entity_id)
    return AuditActivity.objects.create(
        actor=actor,
        created_by=actor,
        action=action,
        entity_type=resolved_type,
        entity_id=resolved_id,
        ip_address=ip_address,
        changes=changes or {},
        metadata=metadata or {},
    )
