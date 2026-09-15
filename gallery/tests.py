import shutil
import tempfile
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.groups import FAMILY_EDITORS
from genealogy.models import Person

from .models import Photo

MEDIA_ROOT = tempfile.mkdtemp()


def image_upload(name="photo.jpg"):
    buffer = BytesIO()
    Image.new("RGB", (24, 24), "teal").save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class GalleryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create(first_name="Wambui")
        cls.editor = User.objects.create_user("editor", password="a-strong-pass-123")
        cls.editor.groups.add(Group.objects.get(name=FAMILY_EDITORS))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_upload_requires_login(self):
        response = self.client.post(reverse("gallery:photo_add"), {"image": image_upload()})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Photo.objects.exists())

    def test_editor_uploads_and_tags_photo(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("gallery:photo_add"),
            {"image": image_upload(), "caption": "Family reunion", "people": [self.person.pk]},
        )
        self.assertRedirects(response, reverse("gallery:photo_list"))
        photo = Photo.objects.get()
        self.assertEqual(photo.uploaded_by, self.editor)
        self.assertEqual(list(photo.people.all()), [self.person])

        listing = self.client.get(reverse("gallery:photo_list"), {"person": self.person.pk})
        self.assertContains(listing, "Family reunion")
        self.assertContains(self.client.get(self.person.get_absolute_url()), photo.image.url)
