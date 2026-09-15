from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PlacesFromTextMigrationTests(TransactionTestCase):
    """Real family records typed before places existed must survive the move to ``Place`` records."""

    before = [("genealogy", "0001_initial")]
    after = [("genealogy", "0002_places_from_text")]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_text_places_become_shared_place_records(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps
        OldPerson, OldEvent = old.get_model("genealogy", "Person"), old.get_model("genealogy", "LifeEvent")
        first = OldPerson.objects.create(first_name="First", birth_place="Nyeri", death_place="Nairobi")
        second = OldPerson.objects.create(first_name="Second", birth_place=" nyeri ")
        OldEvent.objects.create(person=first, place="Nairobi")

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps
        Person, Place, LifeEvent = (new.get_model("genealogy", name) for name in ("Person", "Place", "LifeEvent"))

        self.assertEqual(sorted(Place.objects.values_list("name", flat=True)), ["Nairobi", "Nyeri"])
        first, second = Person.objects.get(pk=first.pk), Person.objects.get(pk=second.pk)
        self.assertEqual(first.birth_place_id, second.birth_place_id)
        self.assertEqual(Place.objects.get(pk=first.death_place_id).name, "Nairobi")
        self.assertIsNone(second.death_place_id)
        self.assertEqual(LifeEvent.objects.get().place_id, first.death_place_id)
