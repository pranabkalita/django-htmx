def update_profile(user, first_name, last_name):
    user.first_name = first_name
    user.last_name = last_name
    user.save(update_fields=['first_name', 'last_name'])


def deactivate_user(user):
    user.is_active = False
    user.save(update_fields=['is_active'])
