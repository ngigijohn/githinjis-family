from django.test import TestCase

from genealogy.models import Person
from genealogy.services.relations import (
    ancestors,
    build_graph,
    descendants,
    generation_count,
    generation_numbers,
    kinship_label,
    relationship_between,
    suggested_root,
)

from .family import build_family


class GenerationNumberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = build_family()

    def test_generations_follow_ancestry_and_married_in_partners(self):
        f = self.f
        expected = {
            f.gg: 1, f.ggm: 1,
            f.g: 2, f.gm: 2,  # Grandma has no recorded parents and takes Grandpa's generation
            f.father: 3, f.mother: 3, f.second_wife: 3, f.uncle: 3, f.uncle_wife: 3, f.aunt: 3,
            f.me: 4, f.wife: 4, f.brother: 4, f.half_brother: 4, f.cousin: 4, f.cousin_husband: 4,
            f.son: 5, f.nephew: 5, f.cousin_child: 5,
        }
        generations = generation_numbers()
        for person, generation in expected.items():
            with self.subTest(person=person.first_name):
                self.assertEqual(generations[person.pk], generation)
        self.assertNotIn(f.stranger.pk, generations)

    def test_tree_nodes_carry_their_generation(self):
        people = {e["data"]["pk"]: e["data"] for e in build_graph()["elements"] if e["data"].get("kind") == "person"}
        self.assertEqual(people[self.f.cousin_child.pk]["generation"], 5)
        self.assertEqual(people[self.f.stranger.pk]["generation"], 1)


class KinshipLabelTests(TestCase):
    def test_labels(self):
        cases = [
            ((1, 0, "M"), "father"),
            ((4, 0, "F"), "great-great-grandmother"),
            ((0, 2, "U"), "grandchild"),
            ((1, 1, "F", True), "half-sister"),
            ((1, 2, "M"), "nephew"),
            ((1, 4, "F"), "great-grandniece"),
            ((4, 1, "M"), "great-great-uncle"),
            ((2, 2, "U"), "first cousin"),
            ((3, 5, "U"), "second cousin twice removed"),
            ((6, 9, "U"), "fifth cousin 3 times removed"),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(kinship_label(*args), expected)


class RelationshipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = build_family()

    def label(self, a, b):
        return relationship_between(a, b).label

    def test_ancestors(self):
        f = self.f
        self.assertEqual(
            ancestors(f.me),
            {f.father.pk: 1, f.mother.pk: 1, f.g.pk: 2, f.gm.pk: 2, f.gg.pk: 3, f.ggm.pk: 3},
        )
        self.assertEqual(set(ancestors(f.me, limit=1)), {f.father.pk, f.mother.pk})

    def test_descendants(self):
        f = self.f
        found = descendants(f.g)
        self.assertEqual(found[f.cousin_child.pk], 3)
        self.assertEqual(found[f.nephew.pk], 3)
        self.assertNotIn(f.wife.pk, found)

    def test_direct_line(self):
        f = self.f
        self.assertEqual(self.label(f.me, f.father), "father")
        self.assertEqual(self.label(f.me, f.gm), "grandmother")
        self.assertEqual(self.label(f.me, f.gg), "great-grandfather")
        self.assertEqual(self.label(f.g, f.me), "grandson")
        self.assertEqual(self.label(f.gg, f.son), "great-great-grandson")

    def test_siblings(self):
        f = self.f
        self.assertEqual(self.label(f.me, f.brother), "brother")
        self.assertEqual(self.label(f.me, f.sister), "sister")
        self.assertEqual(self.label(f.me, f.half_brother), "half-brother")
        self.assertEqual(self.label(f.half_brother, f.sister), "half-sister")

    def test_uncles_aunts_nephews(self):
        f = self.f
        self.assertEqual(self.label(f.me, f.uncle), "uncle")
        self.assertEqual(self.label(f.me, f.aunt), "aunt")
        self.assertEqual(self.label(f.me, f.nephew), "nephew")
        self.assertEqual(self.label(f.uncle, f.nephew), "grandnephew")
        self.assertEqual(self.label(f.nephew, f.uncle), "great-uncle")

    def test_cousins(self):
        f = self.f
        self.assertEqual(self.label(f.me, f.cousin), "first cousin")
        self.assertEqual(self.label(f.me, f.cousin_child), "first cousin once removed")
        self.assertEqual(self.label(f.cousin_child, f.me), "first cousin once removed")
        self.assertEqual(self.label(f.son, f.cousin_child), "second cousin")

    def test_spouses_and_in_laws(self):
        f = self.f
        self.assertEqual(self.label(f.me, f.wife), "wife")
        self.assertEqual(self.label(f.wife, f.me), "husband")
        self.assertEqual(self.label(f.wife, f.father), "father-in-law")
        self.assertEqual(self.label(f.wife, f.mother), "mother-in-law")
        self.assertEqual(self.label(f.father, f.wife), "daughter-in-law")
        self.assertEqual(self.label(f.wife, f.brother), "brother-in-law")
        self.assertEqual(self.label(f.brother, f.wife), "sister-in-law")
        self.assertEqual(self.label(f.me, f.second_wife), "stepmother")
        self.assertEqual(self.label(f.second_wife, f.me), "stepson")
        self.assertEqual(self.label(f.me, f.uncle_wife), "uncle's wife")

    def test_unrelated(self):
        rel = relationship_between(self.f.me, self.f.stranger)
        self.assertEqual(rel.kind, "none")
        self.assertIsNone(rel.label)
        self.assertFalse(rel.found)

    def test_path_and_common_ancestors(self):
        f = self.f
        rel = relationship_between(f.me, f.cousin)
        self.assertEqual(rel.path[0], f.me.pk)
        self.assertEqual(rel.path[-1], f.cousin.pk)
        self.assertEqual(len(rel.path), 5)
        self.assertEqual(set(rel.common_ancestors), {f.g.pk, f.gm.pk})

    def test_generation_count_and_suggested_root(self):
        self.assertEqual(generation_count(), 5)
        self.assertEqual(suggested_root(), self.f.gg.pk)


class BuildGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.f = build_family()

    @staticmethod
    def people(data):
        return {el["data"]["pk"] for el in data["elements"] if el["data"].get("kind") == "person"}

    @staticmethod
    def edges(data):
        return {(el["data"]["source"], el["data"]["target"]) for el in data["elements"] if el["group"] == "edges"}

    def test_window_around_root(self):
        f = self.f
        data = build_graph(f.me, up=1, down=1)
        expected = {f.me, f.father, f.mother, f.brother, f.sister, f.half_brother, f.second_wife, f.wife, f.son}
        self.assertEqual(self.people(data), {p.pk for p in expected})
        self.assertEqual(data["root"], f.me.pk)

        edges = self.edges(data)
        union = f"u{f.parents_union.pk}"
        self.assertIn((f"p{f.father.pk}", union), edges)
        self.assertIn((f"p{f.mother.pk}", union), edges)
        self.assertIn((union, f"p{f.me.pk}"), edges)

    def test_whole_family(self):
        f = self.f
        data = build_graph()
        self.assertEqual(data["count"], Person.objects.count())
        # A child with a single recorded parent hangs directly from that parent.
        self.assertIn((f"p{f.brother.pk}", f"p{f.nephew.pk}"), self.edges(data))

    def test_hides_living_birth_years(self):
        from datetime import date

        f = self.f
        f.son.birth_date = date(2015, 3, 1)
        f.son.save()
        node = lambda data: next(el["data"] for el in data["elements"] if el["data"].get("pk") == f.son.pk)
        self.assertEqual(node(build_graph(f.son, 0, 0))["lifespan"], "b. 2015")
        self.assertEqual(node(build_graph(f.son, 0, 0, hide_living_birth=True))["lifespan"], "")
