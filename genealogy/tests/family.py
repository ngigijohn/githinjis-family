"""A small but tricky family used across the test suite.

    Great-grandpa + Great-grandma
            └── Grandpa + Grandma
                  ├── Father + Mother ──── Me + Wife ── Son
                  │     │           ├── Brother ── Nephew (other parent unknown)
                  │     │           └── Sister
                  │     └ + SecondWife ── HalfBrother
                  ├── Uncle + UncleWife ── Cousin + CousinHusband ── CousinChild
                  └── Aunt
    Stranger (unconnected)
"""
from types import SimpleNamespace

from genealogy.models import ParentChild, Person, Union


def make_person(first, gender="U", **kwargs):
    return Person.objects.create(first_name=first, gender=gender, **kwargs)


def couple(a, b, *children, rtype=ParentChild.Type.BIOLOGICAL):
    union = Union.objects.create(partner_a=a, partner_b=b)
    for child in children:
        for parent in (a, b):
            ParentChild.objects.create(parent=parent, child=child, union=union, relationship_type=rtype)
    return union


def build_family():
    f = SimpleNamespace()
    for name, gender in [
        ("gg", "M"), ("ggm", "F"), ("g", "M"), ("gm", "F"),
        ("father", "M"), ("mother", "F"), ("uncle", "M"), ("aunt", "F"), ("uncle_wife", "F"),
        ("me", "M"), ("brother", "M"), ("sister", "F"), ("second_wife", "F"), ("half_brother", "M"),
        ("cousin", "F"), ("cousin_husband", "M"), ("cousin_child", "M"),
        ("wife", "F"), ("son", "M"), ("nephew", "M"), ("stranger", "U"),
    ]:
        label = "".join(part.capitalize() for part in name.split("_"))
        setattr(f, name, make_person(label, gender))

    couple(f.gg, f.ggm, f.g)
    couple(f.g, f.gm, f.father, f.uncle, f.aunt)
    f.parents_union = couple(f.father, f.mother, f.me, f.brother, f.sister)
    couple(f.father, f.second_wife, f.half_brother)
    couple(f.uncle, f.uncle_wife, f.cousin)
    couple(f.cousin, f.cousin_husband, f.cousin_child)
    f.my_union = couple(f.me, f.wife, f.son)
    f.nephew_link = ParentChild.objects.create(parent=f.brother, child=f.nephew)
    return f
