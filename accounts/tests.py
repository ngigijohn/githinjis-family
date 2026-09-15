from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from genealogy.models import ContactMessage

from .groups import FAMILY_EDITORS


class AccountTests(TestCase):
    def test_family_editors_group_permissions(self):
        group = Group.objects.get(name=FAMILY_EDITORS)
        codenames = set(group.permissions.values_list("codename", flat=True))
        self.assertIn("add_person", codenames)
        self.assertIn("change_person", codenames)
        self.assertIn("add_photo", codenames)
        self.assertNotIn("delete_person", codenames)

    def test_signup_creates_inactive_account_and_notifies_admins(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Wanjiru",
                "last_name": "Githinji",
                "username": "wanjiru",
                "email": "wanjiru@example.com",
                "relationship_note": "Granddaughter of George",
                "password1": "a-strong-pass-123",
                "password2": "a-strong-pass-123",
            },
        )
        self.assertRedirects(response, reverse("accounts:pending"))
        user = User.objects.get(username="wanjiru")
        self.assertFalse(user.is_active)
        self.assertTrue(ContactMessage.objects.filter(message__contains="Granddaughter of George").exists())

    def test_inactive_user_cannot_log_in(self):
        User.objects.create_user("pending", password="a-strong-pass-123", is_active=False)
        response = self.client.post(reverse("accounts:login"), {"username": "pending", "password": "a-strong-pass-123"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout(self):
        self.client.force_login(User.objects.create_user("member"))
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("genealogy:home"))
