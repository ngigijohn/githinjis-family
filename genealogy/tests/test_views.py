import shutil
import tempfile
from datetime import date
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.groups import FAMILY_EDITORS
from genealogy.models import ContactMessage, ParentChild, Person, Union
from genealogy.services.relations import relationship_between

from .family import build_family

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = build_family()
        cls.f.me.birth_date = date(1990, 5, 1)
        cls.f.me.save()
        cls.editor = User.objects.create_user("editor", password="a-strong-pass-123")
        cls.editor.groups.add(Group.objects.get(name=FAMILY_EDITORS))

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_public_pages(self):
        f = self.f
        urls = [
            reverse("genealogy:home"),
            reverse("genealogy:tree"),
            reverse("genealogy:tree") + f"?root={f.me.pk}",
            reverse("genealogy:person_list") + "?q=cousin&status=living&sort=oldest",
            reverse("genealogy:person_detail", args=[f.me.pk]),
            reverse("genealogy:relationship") + f"?a={f.me.pk}&b={f.cousin.pk}",
            reverse("genealogy:relationship") + f"?a={f.me.pk}&b={f.stranger.pk}",
            reverse("genealogy:about"),
            reverse("genealogy:contact"),
            reverse("gallery:photo_list"),
            reverse("accounts:login"),
            reverse("accounts:signup"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_person_list_search(self):
        response = self.client.get(reverse("genealogy:person_list"), {"q": "cousin"})
        self.assertContains(response, "CousinChild")
        self.assertNotContains(response, "Stranger")

    def test_birth_date_hidden_from_visitors(self):
        url = reverse("genealogy:person_detail", args=[self.f.me.pk])
        self.assertNotContains(self.client.get(url), "1 May 1990")
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(url), "1 May 1990")

    def test_editing_requires_login(self):
        f = self.f
        for url in [
            reverse("genealogy:person_add"),
            reverse("genealogy:person_edit", args=[f.me.pk]),
            reverse("gallery:photo_add"),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response["Location"])

    def test_editors_cannot_delete_people(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("genealogy:person_delete", args=[self.f.me.pk]))
        self.assertEqual(response.status_code, 403)

    def test_editor_adds_child_to_a_couple(self):
        f = self.f
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("genealogy:person_add"),
            {
                "of": f.me.pk,
                "relation": "child",
                "relationship_type": "biological",
                "union": f.my_union.pk,
                "first_name": "Baby",
                "gender": "F",
                "is_living": "on",
            },
        )
        baby = Person.objects.get(first_name="Baby")
        self.assertRedirects(response, baby.get_absolute_url())
        self.assertEqual(set(baby.parents()), {f.me, f.wife})
        self.assertEqual(relationship_between(f.son, baby).label, "sister")
        self.assertEqual(baby.created_by, self.editor)

    def test_editor_adds_parent(self):
        f = self.f
        self.client.force_login(self.editor)
        self.client.post(
            reverse("genealogy:person_add"),
            {"of": f.nephew.pk, "relation": "parent", "relationship_type": "biological", "first_name": "NephewMum", "gender": "F", "is_living": "on"},
        )
        self.assertIn("NephewMum", [p.first_name for p in f.nephew.parents()])

    def test_add_person_form_shows_validation_errors(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("genealogy:person_add"),
            {"of": self.f.me.pk, "relation": "parent", "relationship_type": "biological", "first_name": "Third", "gender": "M"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has two biological parents")
        self.assertFalse(Person.objects.filter(first_name="Third").exists())

    def test_link_existing_people(self):
        f = self.f
        self.client.force_login(self.editor)
        self.client.post(
            reverse("genealogy:person_link", args=[f.stranger.pk]),
            {"relation": "partner", "relative": f.aunt.pk, "union_type": "marriage"},
        )
        self.assertTrue(Union.objects.filter(partner_a=f.stranger, partner_b=f.aunt).exists())

    def test_link_rejects_loops(self):
        f = self.f
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("genealogy:person_link", args=[f.me.pk]),
            {"relation": "child", "relative": f.g.pk, "relationship_type": "biological"},
            follow=True,
        )
        self.assertFalse(ParentChild.objects.filter(parent=f.me, child=f.g).exists())
        self.assertContains(response, "would create a loop")

    def test_unlink(self):
        f = self.f
        self.client.force_login(self.editor)
        self.client.post(
            reverse("genealogy:person_unlink", args=[f.brother.pk]),
            {"kind": "parentchild", "id": f.nephew_link.pk},
        )
        self.assertFalse(ParentChild.objects.filter(pk=f.nephew_link.pk).exists())

    def test_unlink_requires_permission(self):
        response = self.client.post(
            reverse("genealogy:person_unlink", args=[self.f.brother.pk]),
            {"kind": "parentchild", "id": self.f.nephew_link.pk},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ParentChild.objects.filter(pk=self.f.nephew_link.pk).exists())

    def test_life_events(self):
        f = self.f
        self.client.force_login(self.editor)
        self.client.post(
            reverse("genealogy:event_add", args=[f.me.pk]),
            {"event_type": "education", "title": "Graduated", "date": "2012-11-30", "place": "Nairobi"},
        )
        self.assertContains(self.client.get(f.me.get_absolute_url()), "Graduated")

    def test_contact_form(self):
        response = self.client.post(
            reverse("genealogy:contact"),
            {"name": "Wanjiku", "email": "wanjiku@example.com", "message": "Please add my grandmother."},
        )
        self.assertRedirects(response, reverse("genealogy:contact"))
        self.assertTrue(ContactMessage.objects.filter(name="Wanjiku").exists())


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = build_family()
        cls.f.me.birth_date = date(1990, 5, 1)
        cls.f.me.save()

    def test_tree(self):
        f = self.f
        response = self.client.get(reverse("genealogy:api_tree"), {"root": f.me.pk, "up": 1, "down": 0})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        me = next(el["data"] for el in data["elements"] if el["data"].get("pk") == f.me.pk)
        self.assertEqual(me["lifespan"], "")  # hidden from anonymous visitors
        self.assertTrue(me["root"])

        self.client.force_login(User.objects.create_user("viewer"))
        data = self.client.get(reverse("genealogy:api_tree"), {"root": f.me.pk}).json()
        me = next(el["data"] for el in data["elements"] if el["data"].get("pk") == f.me.pk)
        self.assertEqual(me["lifespan"], "b. 1990")

    def test_tree_unknown_root(self):
        self.assertEqual(self.client.get(reverse("genealogy:api_tree"), {"root": 999999}).status_code, 404)

    def test_search(self):
        results = self.client.get(reverse("genealogy:api_people_search"), {"q": "cousin"}).json()["results"]
        self.assertEqual({r["name"] for r in results}, {"Cousin", "CousinHusband", "CousinChild"})

    def test_relationship(self):
        f = self.f
        data = self.client.get(reverse("genealogy:api_relationship"), {"a": f.me.pk, "b": f.brother.pk}).json()
        self.assertEqual(data["label"], "brother")
        self.assertEqual(data["sentence"], "Brother is Me's brother.")
        self.assertEqual(self.client.get(reverse("genealogy:api_relationship")).status_code, 400)


class SeedCommandTests(TestCase):
    def test_seed_family(self):
        call_command("seed_family", "--no-photos", stdout=StringIO())
        self.assertEqual(Person.objects.count(), 12)
        john_sr = Person.objects.get(first_name="John", nickname="Sr.")
        john = Person.objects.get(first_name="John", nickname="")
        michelle = Person.objects.get(first_name="Michelle")
        victor = Person.objects.get(first_name="Victor")
        self.assertEqual(relationship_between(john, victor).label, "brother")
        self.assertEqual(relationship_between(michelle, john_sr).label, "grandfather")
        self.assertEqual(relationship_between(john_sr, michelle).label, "granddaughter")
