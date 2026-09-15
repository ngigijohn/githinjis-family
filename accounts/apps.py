from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Family accounts"

    def ready(self):
        from .groups import ensure_family_editors_group

        # accounts is the last installed app, so permissions for the genealogy
        # and gallery apps already exist when this runs.
        post_migrate.connect(ensure_family_editors_group, sender=self)
