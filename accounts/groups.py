from django.db import DEFAULT_DB_ALIAS

FAMILY_EDITORS = "Family Editors"

# Editors can add and update everything. Deleting whole people is left to admins.
EDITOR_PERMISSIONS = {
    "genealogy": {
        "person": ["add", "change", "view"],
        "union": ["add", "change", "delete", "view"],
        "parentchild": ["add", "change", "delete", "view"],
        "lifeevent": ["add", "change", "delete", "view"],
        "residence": ["add", "change", "delete", "view"],
        "education": ["add", "change", "delete", "view"],
        "employment": ["add", "change", "delete", "view"],
        "place": ["add", "change", "view"],
        "tag": ["add", "change", "view"],
    },
    "gallery": {
        "photo": ["add", "change", "delete", "view"],
        "recording": ["add", "change", "delete", "view"],
    },
}


def ensure_family_editors_group(using=DEFAULT_DB_ALIAS, **kwargs):
    from django.contrib.auth.models import Group, Permission

    group, _ = Group.objects.using(using).get_or_create(name=FAMILY_EDITORS)
    for app_label, models in EDITOR_PERMISSIONS.items():
        codenames = [f"{action}_{model}" for model, actions in models.items() for action in actions]
        permissions = Permission.objects.using(using).filter(
            content_type__app_label=app_label, codename__in=codenames
        )
        group.permissions.add(*permissions)
    return group
