import shutil
import tempfile
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.groups import FAMILY_EDITORS
from gallery.models import Recording
from genealogy.models import Bookmark, Education, Place, Residence, Tag

from .family import build_family

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class LifeHistoryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = f = build_family()
        cls.othaya = Place.from_text("Othaya, Nyeri, Kenya")
        cls.kenya = cls.othaya.parent.parent
        Residence.objects.create(person=f.me, place=cls.othaya, start_year=2010, is_current=True)
        Education.objects.create(person=f.me, institution="University of Nairobi", place=Place.from_text("Nairobi, Kenya"), start_year=2008, end_year=2012)
        f.me.tags.add(Tag.objects.create(name="Teacher", category=Tag.Category.OCCUPATION))
        for person, born in ((f.me, date(1990, 1, 1)), (f.brother, date(1992, 1, 1)), (f.sister, date(1995, 1, 1))):
            person.birth_date = born
            person.save()
        cls.recording = Recording.objects.create(title="How we came to Othaya", audio=SimpleUploadedFile("story.wav", b"RIFF"), place=cls.othaya)
        cls.recording.speakers.add(f.g)
        cls.editor = User.objects.create_user("editor", password="a-strong-pass-123")
        cls.editor.groups.add(Group.objects.get(name=FAMILY_EDITORS))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_pages_load(self):
        f = self.f
        urls = [
            reverse("genealogy:place_list"),
            reverse("genealogy:place_detail", args=[self.othaya.pk]),
            reverse("genealogy:place_detail", args=[self.kenya.pk]),
            reverse("genealogy:tag_list"),
            reverse("genealogy:tag_detail", args=["teacher"]),
            reverse("genealogy:person_detail", args=[f.me.pk]),
            reverse("genealogy:person_list") + f"?place={self.kenya.pk}&tag=teacher",
            reverse("gallery:recording_list"),
            reverse("gallery:recording_detail", args=[self.recording.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.editor)
        for url in [reverse("genealogy:bookmarks"), reverse("gallery:recording_add"), reverse("genealogy:person_edit", args=[f.me.pk])]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_place_counts_include_places_inside(self):
        response = self.client.get(reverse("genealogy:place_list"))
        kenya = next(node for node in response.context["nodes"] if node["place"] == self.kenya)
        self.assertIn(self.f.me.pk, kenya["people"])

    def test_people_filtered_by_place_and_tag(self):
        response = self.client.get(reverse("genealogy:person_list"), {"place": self.kenya.pk, "tag": "teacher"})
        self.assertEqual([p.pk for p in response.context["people"]], [self.f.me.pk])

    def test_current_home_of_living_relative_is_private(self):
        url = reverse("genealogy:place_detail", args=[self.othaya.pk])
        self.assertNotContains(self.client.get(url), "Lives here now")
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), "Lives here now")

    def test_editor_adds_and_removes_history(self):
        f = self.f
        self.client.force_login(self.editor)
        add = reverse("genealogy:history_add", args=[f.me.pk, "home"])
        self.client.post(add, {"home-place": "Karatina, Nyeri, Kenya", "home-start_year": 2001, "home-end_year": 2005})
        home = Residence.objects.get(person=f.me, place__name="Karatina")
        self.assertEqual(home.place.parent, self.othaya.parent)

        self.client.post(add, {"home-place": "Nanyuki", "home-start_year": 2005, "home-end_year": 2001})
        self.assertFalse(Residence.objects.filter(place__name="Nanyuki").exists())

        self.client.post(reverse("genealogy:history_delete", args=["home", home.pk]))
        self.assertFalse(Residence.objects.filter(pk=home.pk).exists())

    def test_history_requires_permission(self):
        response = self.client.post(reverse("genealogy:history_add", args=[self.f.me.pk, "work"]), {"work-employer": "Somewhere"})
        self.assertEqual(response.status_code, 403)

    def test_bookmark_toggle(self):
        self.client.force_login(self.editor)
        url = reverse("genealogy:bookmark_toggle", args=[self.f.aunt.pk])
        self.client.post(url)
        self.assertTrue(Bookmark.objects.filter(user=self.editor, person=self.f.aunt).exists())
        self.client.post(url)
        self.assertFalse(Bookmark.objects.filter(user=self.editor, person=self.f.aunt).exists())

    def test_profile_form_saves_places_tags_and_namesake(self):
        f = self.f
        self.client.force_login(self.editor)
        self.client.post(
            reverse("genealogy:person_edit", args=[f.aunt.pk]),
            {"first_name": "Aunt", "gender": "F", "is_living": "on", "birth_place": "Kagio, Kirinyaga",
             "homeland": "Othaya, Nyeri, Kenya", "tag_names": "Teacher, Choir member", "named_after": f.gm.pk},
        )
        f.aunt.refresh_from_db()
        self.assertEqual(f.aunt.birth_place.full_name, "Kagio, Kirinyaga")
        self.assertEqual(f.aunt.homeland, self.othaya)
        self.assertEqual(sorted(f.aunt.tags.values_list("name", flat=True)), ["Choir member", "Teacher"])
        self.assertEqual(f.aunt.named_after, f.gm)

    def test_birth_order_and_marital_status(self):
        f = self.f
        self.assertEqual(f.me.birth_order_label, "1st son · Firstborn")
        self.assertEqual(f.brother.birth_order_label, "2nd son · 2nd child")
        self.assertEqual(f.sister.birth_order_label, "1st daughter · Lastborn")
        self.assertEqual(f.half_brother.birth_order_label, "Only child")
        self.assertEqual(f.me.marital_status, "Married")

    def test_editor_uploads_recording(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse("gallery:recording_add"),
            {"title": "Songs", "audio": SimpleUploadedFile("songs.mp3", b"ID3"), "language": "Gĩkũyũ", "place": "Othaya, Nyeri, Kenya", "speakers": [self.f.gm.pk]},
        )
        recording = Recording.objects.get(title="Songs")
        self.assertEqual(recording.place, self.othaya)
        self.assertEqual(list(recording.speakers.all()), [self.f.gm])

    def test_tree_api_includes_card_details(self):
        self.client.force_login(self.editor)
        data = self.client.get(reverse("genealogy:api_tree"), {"root": self.f.me.pk}).json()
        me = next(el["data"] for el in data["elements"] if el["data"].get("pk") == self.f.me.pk)
        self.assertEqual(me["birthOrder"], "1st son · Firstborn")
        self.assertEqual(me["tags"], ["Teacher"])
        self.assertEqual(me["marital"], "Married")
        self.assertEqual(me["children"], 1)
