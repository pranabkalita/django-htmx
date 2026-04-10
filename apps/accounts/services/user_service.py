from apps.accounts.services.audit_log_service import log_activity


def update_profile(user, first_name, last_name, *, actor=None):
    changes = {}
    if user.first_name != first_name:
        changes['first_name'] = {'from': user.first_name, 'to': first_name}
    if user.last_name != last_name:
        changes['last_name'] = {'from': user.last_name, 'to': last_name}

    user.first_name = first_name
    user.last_name = last_name
    user.save(update_fields=['first_name', 'last_name'])
    if changes:
        log_activity(action='user_profile_updated', actor=actor or user, entity=user, changes=changes)


def deactivate_user(user, *, actor=None):
    user.is_active = False
    user.soft_delete(deleted_by=actor or user, update_fields=['is_active'])
    log_activity(action='user_deactivated', actor=actor or user, entity=user)
