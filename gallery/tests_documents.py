import shutil
import tempfile

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.groups import FAMILY_EDITORS
from genealogy.models import Person

from .models import Document

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DocumentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create(first_name="Wanjiru", gender="F")
        cls.editor = User.objects.create_user("editor", password="a-strong-pass-123")
        cls.editor.groups.add(Group.objects.get(name=FAMILY_EDITORS))
        cls.public = Document.objects.create(
            title="Land title, Othaya",
            document_type=Document.Type.LAND,
            file=SimpleUploadedFile("land.pdf", b"%PDF-1.4 land"),
            privacy=Document.Privacy.PUBLIC,
        )
        cls.private = Document.objects.create(
            title="Birth certificate",
            document_type=Document.Type.BIRTH,
            file=SimpleUploadedFile("birth.pdf", b"%PDF-1.4 birth"),
        )
        cls.private.people.add(cls.person)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_family_only_documents_are_hidden_from_visitors(self):
        response = self.client.get(reverse("gallery:document_list"))
        self.assertContains(response, "Land title, Othaya")
        self.assertNotContains(response, "Birth certificate")
        self.assertEqual(response.context["hidden_count"], 1)
        self.assertEqual(self.client.get(self.private.get_absolute_url()).status_code, 404)

        self.client.force_login(self.editor)
        signed_in = self.client.get(reverse("gallery:document_list"))
        self.assertContains(signed_in, "Birth certificate")
        self.assertEqual(self.client.get(self.private.get_absolute_url()).status_code, 200)

    def test_profile_shows_only_documents_you_may_see(self):
        url = reverse("genealogy:person_detail", args=[self.person.pk])
        self.assertNotContains(self.client.get(url), "Birth certificate")
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), "Birth certificate")

    def test_editor_adds_a_document(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("gallery:document_add"),
            {
                "title": "Marriage certificate",
                "document_type": Document.Type.MARRIAGE,
                "file": SimpleUploadedFile("marriage.jpg", b"\xff\xd8\xff jpeg"),
                "place": "Othaya, Nyeri, Kenya",
                "source": "Kept by the family",
                "privacy": Document.Privacy.FAMILY,
                "people": [self.person.pk],
            },
        )
        document = Document.objects.get(title="Marriage certificate")
        self.assertRedirects(response, document.get_absolute_url())
        self.assertEqual(document.place.full_name, "Othaya, Nyeri, Kenya")
        self.assertEqual(list(document.people.all()), [self.person])
        self.assertEqual(document.uploaded_by, self.editor)

    def test_adding_requires_permission(self):
        response = self.client.get(reverse("gallery:document_add"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_tabs_link_the_three_kinds_of_memory(self):
        response = self.client.get(reverse("gallery:photo_list"))
        for url in [reverse("gallery:photo_list"), reverse("gallery:recording_list"), reverse("gallery:document_list")]:
            self.assertContains(response, f'href="{url}"')
