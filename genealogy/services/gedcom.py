"""Export the family as GEDCOM 5.5.1, the format genealogy programs exchange.

GEDCOM is how a family moves its records between products, so this is the
family's way out of this site: Ancestry, MyHeritage, Gramps and the rest all
read it. Only what the site actually records is written, and nothing is
invented to fill a gap.
"""
from datetime import date

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
GENDER = {"M": "M", "F": "F"}


def _date(value, approx=False):
    """``2 JAN 1950`` as GEDCOM writes it, or ``ABT 1950`` when only the year is trusted."""
    if not value:
        return ""
    if approx:
        return f"ABT {value.year}"
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def _clean(text):
    return " ".join(str(text or "").split())


def _name(person):
    """GEDCOM puts the surname between slashes."""
    given = " ".join(part for part in (person.first_name, person.middle_name) if part)
    surname = person.last_name or ""
    return f"{_clean(given)} /{_clean(surname)}/".strip()


def _event(lines, tag, when="", place="", approx=False):
    if not when and not place:
        return
    lines.append(f"1 {tag}")
    if when:
        lines.append(f"2 DATE {when}" if isinstance(when, str) else f"2 DATE {_date(when, approx)}")
    if place:
        lines.append(f"2 PLAC {_clean(place)}")


def export(site_name="Family", include_living=True):
    """The whole family as GEDCOM text.

    ``include_living`` writes dates for living relatives; leave it off to share
    the file outside the family, which keeps their birth dates private.
    """
    from genealogy.models import ParentChild, Person, Union

    people = list(
        Person.objects.select_related("birth_place__parent", "death_place__parent").prefetch_related("tags").order_by("pk")
    )
    unions = list(Union.objects.select_related("partner_a", "partner_b").order_by("pk"))
    links = list(ParentChild.objects.select_related("child", "parent", "union").order_by("pk"))

    # Which family record each person belongs to as a child, and as a partner.
    families = {union.pk: {"husband": None, "wife": None, "others": [], "children": [], "union": union} for union in unions}
    for union in unions:
        for partner in (union.partner_a, union.partner_b):
            if partner is None:
                continue
            slot = "husband" if partner.gender == "M" else "wife" if partner.gender == "F" else None
            if slot and families[union.pk][slot] is None:
                families[union.pk][slot] = partner
            else:
                families[union.pk]["others"].append(partner)

    # Children whose parents have no union recorded still need a family record.
    extra = {}
    for link in links:
        if link.union_id and link.union_id in families:
            families[link.union_id]["children"].append(link)
            continue
        key = ("solo", link.parent_id)
        if key not in extra:
            extra[key] = {"husband": None, "wife": None, "others": [], "children": [], "union": None}
            slot = "husband" if link.parent.gender == "M" else "wife" if link.parent.gender == "F" else "others"
            if slot == "others":
                extra[key]["others"].append(link.parent)
            else:
                extra[key][slot] = link.parent
        extra[key]["children"].append(link)

    ordered = [(f"F{index}", data) for index, data in enumerate(list(families.values()) + list(extra.values()), start=1)]
    family_of_child = {}
    families_of_partner = {}
    for fid, data in ordered:
        for link in data["children"]:
            family_of_child.setdefault(link.child_id, fid)
        for partner in [data["husband"], data["wife"], *data["others"]]:
            if partner is not None:
                families_of_partner.setdefault(partner.pk, []).append(fid)

    lines = [
        "0 HEAD",
        "1 SOUR OUR-ROOTS",
        f"2 NAME {_clean(site_name)}",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        f"1 DATE {_date(date.today())}",
    ]

    for person in people:
        hide = person.is_living and not include_living
        lines.append(f"0 @I{person.pk}@ INDI")
        lines.append(f"1 NAME {_name(person)}")
        if person.nickname:
            lines.append(f"2 NICK {_clean(person.nickname)}")
        if person.maiden_name:
            lines.append(f"1 NAME /{_clean(person.maiden_name)}/")
            lines.append("2 TYPE maiden")
        if person.gender in GENDER:
            lines.append(f"1 SEX {GENDER[person.gender]}")
        birth_place = person.birth_place.full_name if person.birth_place else ""
        if not hide:
            _event(lines, "BIRT", person.birth_date, birth_place, person.birth_date_approx)
        elif birth_place:
            _event(lines, "BIRT", "", birth_place)
        if not person.is_living:
            _event(lines, "DEAT", person.death_date, person.death_place.full_name if person.death_place else "")
        for tag in person.tags.all():
            lines.append(f"1 OCCU {_clean(tag.name)}")
        if person.lineage:
            lines.append(f"1 NOTE Clan: {_clean(person.lineage)}")
        if person.biography and not hide:
            biography = _clean(person.biography)
            lines.append(f"1 NOTE {biography[:200]}")
            for start in range(200, len(biography), 200):
                lines.append(f"2 CONC {biography[start:start + 200]}")
        if person.pk in family_of_child:
            lines.append(f"1 FAMC @{family_of_child[person.pk]}@")
        for fid in families_of_partner.get(person.pk, []):
            lines.append(f"1 FAMS @{fid}@")

    for fid, data in ordered:
        lines.append(f"0 @{fid}@ FAM")
        if data["husband"]:
            lines.append(f"1 HUSB @I{data['husband'].pk}@")
        if data["wife"]:
            lines.append(f"1 WIFE @I{data['wife'].pk}@")
        for partner in data["others"]:
            lines.append(f"1 ASSO @I{partner.pk}@")
            lines.append("2 RELA partner")
        seen = set()
        for link in data["children"]:
            if link.child_id in seen:
                continue
            seen.add(link.child_id)
            lines.append(f"1 CHIL @I{link.child_id}@")
            if link.relationship_type != "biological":
                lines.append(f"2 PEDI {link.relationship_type}")
        union = data["union"]
        if union:
            tag = "MARR" if union.union_type != "partnership" else "EVEN"
            _event(lines, tag, union.start_date, "")
            if union.end_date or union.end_reason:
                _event(lines, "DIV" if union.end_reason == "divorce" else "EVEN", union.end_date, "")

    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"
