from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from genealogy.models import ParentChild, Person, Place
from genealogy.services.gedcom import export

from .family import build_family


class GedcomExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = f = build_family()
        f.gg.birth_date, f.gg.death_date = date(1901, 3, 4), date(1980, 7, 9)
        f.gg.birth_place = Place.from_text("Othaya, Nyeri, Kenya")
        f.gg.last_name, f.gg.lineage = "Kamau", "Anjirũ"
        f.gg.save()
        f.me.birth_date = date(1990, 5, 1)
        f.me.maiden_name = ""
        f.me.save()

    def lines(self, **kwargs):
        return export(**kwargs).splitlines()

    def test_structure_and_people(self):
        lines = self.lines()
        self.assertEqual(lines[0], "0 HEAD")
        self.assertEqual(lines[-1], "0 TRLR")
        self.assertIn("2 VERS 5.5.1", lines)
        self.assertIn(f"0 @I{self.f.gg.pk}@ INDI", lines)
        self.assertIn("1 NAME Gg /Kamau/", lines)
        self.assertIn("1 SEX M", lines)
        self.assertIn("2 DATE 4 MAR 1901", lines)
        self.assertIn("2 PLAC Othaya, Nyeri, Kenya", lines)
        self.assertIn("2 DATE 9 JUL 1980", lines)
        self.assertIn("1 NOTE Clan: Anjirũ", lines)

    def test_families_link_parents_and_children(self):
        text = export()
        me = f"0 @I{self.f.me.pk}@ INDI"
        self.assertIn(me, text)
        # Me belongs to a family as a child, and to their own as a partner.
        block = text.split(me)[1].split("0 @")[0]
        self.assertIn("1 FAMC @F", block)
        self.assertIn("1 FAMS @F", block)
        self.assertIn(f"1 CHIL @I{self.f.son.pk}@", text)
        self.assertIn(f"1 HUSB @I{self.f.me.pk}@", text)
        self.assertIn(f"1 WIFE @I{self.f.wife.pk}@", text)

    def test_non_biological_links_keep_their_kind(self):
        ParentChild.objects.create(parent=self.f.aunt, child=self.f.nephew, relationship_type=ParentChild.Type.ADOPTED)
        self.assertIn("2 PEDI adopted", export())

    def test_living_relatives_dates_can_be_left_out(self):
        self.assertIn("2 DATE 1 MAY 1990", export())
        without = export(include_living=False)
        self.assertNotIn("2 DATE 1 MAY 1990", without)
        self.assertIn("2 DATE 4 MAR 1901", without)  # people who have died are still described

    def test_download_requires_signing_in(self):
        url = reverse("genealogy:gedcom_export")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

        self.client.force_login(User.objects.create_user("relative"))
        download = self.client.get(url)
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment; filename=", download["Content-Disposition"])
        self.assertTrue(download.content.decode().startswith("0 HEAD"))

        without = self.client.get(url, {"living": "no"})
        self.assertIn("without-living", without["Content-Disposition"])
