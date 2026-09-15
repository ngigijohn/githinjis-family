from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from genealogy.models import ParentChild, Person, Union

from .family import build_family, make_person


class PersonTests(TestCase):
    def test_names(self):
        person = Person(first_name="John", middle_name="Kamau", last_name="Ngigi", nickname="Sr.")
        self.assertEqual(person.full_name, "John Kamau Ngigi")
        self.assertEqual(person.display_name, "John Kamau Ngigi (Sr.)")
        self.assertEqual(person.initials, "JN")

    def test_lifespan_text(self):
        living = Person(first_name="A", birth_date=date(1990, 1, 1))
        self.assertEqual(living.lifespan_text(), "b. 1990")
        self.assertEqual(living.lifespan_text(hide_living_birth=True), "")

        deceased = Person(first_name="B", birth_date=date(1920, 1, 1), birth_date_approx=True, death_date=date(1990, 6, 1), is_living=False)
        self.assertEqual(deceased.lifespan_text(hide_living_birth=True), "c. 1920 – 1990")
        self.assertEqual(Person(first_name="C", is_living=False).lifespan_text(), "Deceased")

    def test_death_date_marks_person_deceased(self):
        person = make_person("D", death_date=date(2001, 1, 1))
        self.assertFalse(person.is_living)

    def test_death_before_birth_is_invalid(self):
        person = Person(first_name="E", birth_date=date(2000, 1, 1), death_date=date(1999, 1, 1))
        with self.assertRaises(ValidationError):
            person.full_clean()

    def test_age(self):
        person = Person(first_name="F", birth_date=date(1950, 6, 15), death_date=date(2000, 6, 14), is_living=False)
        self.assertEqual(person.age, 49)


class RelationshipValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = build_family()

    def test_cannot_create_ancestry_loop(self):
        with self.assertRaisesMessage(ValidationError, "would create a loop"):
            ParentChild(parent=self.f.me, child=self.f.g).full_clean()

    def test_at_most_two_biological_parents(self):
        with self.assertRaisesMessage(ValidationError, "two biological parents"):
            ParentChild(parent=self.f.stranger, child=self.f.me).full_clean()
        # Adoptive parents are fine.
        ParentChild(parent=self.f.stranger, child=self.f.me, relationship_type=ParentChild.Type.ADOPTED).full_clean()

    def test_reverse_duplicate_union_is_invalid(self):
        with self.assertRaises(ValidationError):
            Union(partner_a=self.f.mother, partner_b=self.f.father).full_clean()

    def test_parent_must_belong_to_union(self):
        with self.assertRaises(ValidationError):
            ParentChild(parent=self.f.stranger, child=self.f.aunt, union=self.f.parents_union, relationship_type=ParentChild.Type.STEP).full_clean()

    def test_attach_unions(self):
        a, b, child = make_person("A"), make_person("B"), make_person("Child")
        union = Union.objects.create(partner_a=a, partner_b=b)
        ParentChild.objects.create(parent=a, child=child)
        ParentChild.objects.create(parent=b, child=child)
        ParentChild.attach_unions(child)
        self.assertEqual(set(ParentChild.objects.filter(child=child).values_list("union_id", flat=True)), {union.pk})
