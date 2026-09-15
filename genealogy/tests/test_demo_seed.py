import shutil
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from gallery.models import Photo, Recording
from genealogy.models import Education, Employment, ParentChild, Person, Place, Residence, Tag, Union
from genealogy.services.relations import generation_count

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DemoSeedTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def seed(self, *args):
        call_command("seed_demo", "--people", "90", "--no-users", *args, stdout=StringIO())

    def test_builds_a_varied_family(self):
        self.seed("--no-media")
        self.assertGreaterEqual(Person.objects.count(), 60)
        self.assertGreaterEqual(generation_count(), 5)
        self.assertTrue(Person.objects.filter(named_after__isnull=False).exists())
        self.assertTrue(Person.objects.filter(birth_order__isnull=False, birth_date__isnull=True).exists())
        self.assertTrue(Person.objects.filter(maiden_name__gt="").exists())
        self.assertTrue(Union.objects.exclude(end_reason="").exists())
        self.assertTrue(ParentChild.objects.exclude(relationship_type=ParentChild.Type.BIOLOGICAL).exists())
        self.assertTrue(Place.objects.filter(latitude__isnull=False, parent__isnull=False).exists())
        for model in (Residence, Education, Employment, Tag):
            with self.subTest(model=model.__name__):
                self.assertTrue(model.objects.exists())
        self.assertEqual(Residence.objects.filter(is_current=True, person__is_living=False).count(), 0)

    def test_relationship_rules_hold(self):
        self.seed("--no-media")
        for link in ParentChild.objects.select_related("parent", "child", "union"):
            link.full_clean()

    def test_same_seed_builds_the_same_family(self):
        self.seed("--no-media")
        first = list(Person.objects.order_by("pk").values_list("first_name", "last_name"))
        self.seed("--no-media", "--reset")
        self.assertEqual(list(Person.objects.order_by("pk").values_list("first_name", "last_name")), first)

    def test_media(self):
        self.seed()
        self.assertTrue(Photo.objects.filter(people__isnull=False).exists())
        self.assertTrue(Recording.objects.filter(speakers__isnull=False).exists())
