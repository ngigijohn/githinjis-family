"""Graph algorithms over the family: ancestry, kinship naming and tree data.

All relationships are loaded into memory once (``FamilyIndex``) and then
walked with breadth-first search, which keeps the number of queries constant
no matter how deep the family goes.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


def _pk(obj):
    return getattr(obj, "pk", obj)


@dataclass
class FamilyIndex:
    parents: dict = field(default_factory=lambda: defaultdict(set))
    children: dict = field(default_factory=lambda: defaultdict(set))
    partners: dict = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def load(cls):
        from genealogy.models import ParentChild, Union

        index = cls()
        for parent_id, child_id in ParentChild.objects.values_list("parent_id", "child_id"):
            index.parents[child_id].add(parent_id)
            index.children[parent_id].add(child_id)
        for a, b in Union.objects.exclude(partner_b=None).values_list("partner_a_id", "partner_b_id"):
            index.partners[a].add(b)
            index.partners[b].add(a)
        return index


def _walk(start, edges, limit=None):
    """Breadth-first walk. Returns ``{person_id: (distance, previous_id)}`` including ``start``."""
    seen = {start: (0, None)}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        distance = seen[current][0]
        if limit is not None and distance >= limit:
            continue
        for nxt in sorted(edges.get(current, ())):
            if nxt not in seen:
                seen[nxt] = (distance + 1, current)
                queue.append(nxt)
    return seen


def ancestors(person, index=None, limit=None):
    """``{ancestor_id: generations_up}`` for a person (the person is excluded)."""
    index = index or FamilyIndex.load()
    walk = _walk(_pk(person), index.parents, limit)
    return {pid: dist for pid, (dist, _) in walk.items() if dist > 0}


def descendants(person, index=None, limit=None):
    """``{descendant_id: generations_down}`` for a person (the person is excluded)."""
    index = index or FamilyIndex.load()
    walk = _walk(_pk(person), index.children, limit)
    return {pid: dist for pid, (dist, _) in walk.items() if dist > 0}


def generation_count(index=None):
    """Length of the longest parent→child chain recorded (0 when there are no links)."""
    index = index or FamilyIndex.load()
    memo, visiting = {}, set()

    def depth(pid):
        if pid in memo:
            return memo[pid]
        if pid in visiting:  # defensive: validation prevents cycles
            return 0
        visiting.add(pid)
        result = 1 + max((depth(child) for child in index.children.get(pid, ())), default=0)
        visiting.discard(pid)
        memo[pid] = result
        return result

    return max((depth(pid) for pid in list(index.children)), default=0)


def generation_numbers(index=None):
    """``{person_id: generation}``, counting 1 at the eldest recorded ancestors.

    Partners share a generation and children sit one below their parents. So
    someone who married into the family lines up with their partner, and an
    in-law's own parents and grandparents sit above them rather than at the top.
    """
    index = index or FamilyIndex.load()
    people = set(index.parents) | set(index.children) | set(index.partners)

    # Partners share a generation, so work with groups of partners.
    leader = {pid: pid for pid in people}

    def find(pid):
        while leader[pid] != pid:
            leader[pid] = leader[leader[pid]]
            pid = leader[pid]
        return pid

    for pid in people:
        for partner in index.partners.get(pid, ()):
            leader[find(pid)] = find(partner)
    groups = {find(pid) for pid in people}
    parent_groups, child_groups = defaultdict(set), defaultdict(set)
    for child, parents in index.parents.items():
        for parent in parents:
            upper, lower = find(parent), find(child)
            if upper != lower:
                parent_groups[lower].add(upper)
                child_groups[upper].add(lower)

    def memoized(step):
        memo, visiting = {}, set()

        def solve(group):
            if group not in memo:
                if group in visiting:  # defensive: validation prevents loops
                    return 1
                visiting.add(group)
                memo[group] = step(group, solve)
                visiting.discard(group)
            return memo[group]

        return solve

    # One below the lowest recorded parents...
    depth = memoized(lambda group, solve: 1 + max((solve(p) for p in parent_groups[group]), default=0))
    # ...then lift ancestors who sit higher than needed to just above their children.
    placed = memoized(
        lambda group, solve: max(depth(group), min((solve(c) for c in child_groups[group]), default=depth(group) + 1) - 1)
    )
    return {pid: placed(find(pid)) for pid in people}


def _birth_label(position, same_gender, total, gender):
    from genealogy.models import ordinal

    if total == 1:
        return "Only child"
    parts = []
    noun = {"M": "son", "F": "daughter"}.get(gender)
    if noun and same_gender:
        parts.append(f"{ordinal(same_gender)} {noun}")
    parts.append("Firstborn" if position == 1 else "Lastborn" if position == total else f"{ordinal(position)} child")
    return " · ".join(parts)


def birth_order_labels(person_ids, index=None):
    """``{person_id: label}`` such as ``"2nd son · 3rd child"``, among children of the same parents.

    Siblings are ordered by recorded birth order when all of them have one,
    otherwise by birth date. People whose place can't be told get no label.
    """
    from genealogy.models import Person

    index = index or FamilyIndex.load()
    wanted = set(person_ids)
    families = {}
    for pid in wanted:
        parents = frozenset(index.parents.get(pid, ()))
        if parents and parents not in families:
            shared = set.intersection(*(set(index.children.get(parent, ())) for parent in parents))
            families[parents] = {child for child in shared if frozenset(index.parents.get(child, ())) == parents}
    ids = set().union(*families.values()) if families else set()
    facts = {row["pk"]: row for row in Person.objects.filter(pk__in=ids).values("pk", "gender", "birth_date", "birth_order")}

    labels = {}
    for children in families.values():
        kids = [facts[child] for child in children if child in facts]
        if len(kids) == 1 or all(kid["birth_order"] for kid in kids):
            order = sorted(kids, key=lambda kid: (kid["birth_order"] or 0, kid["pk"]))
        elif all(kid["birth_date"] for kid in kids):
            order = sorted(kids, key=lambda kid: (kid["birth_date"], kid["pk"]))
        else:
            for kid in kids:
                if kid["pk"] in wanted and kid["birth_order"]:
                    labels[kid["pk"]] = _birth_label(kid["birth_order"], None, len(kids), kid["gender"])
            continue
        for position, kid in enumerate(order, start=1):
            if kid["pk"] in wanted:
                same = sum(1 for other in order[:position] if other["gender"] == kid["gender"])
                labels[kid["pk"]] = _birth_label(position, same, len(order), kid["gender"])
    return labels


def suggested_root(index=None):
    """The founding ancestor with the most descendants: a sensible starting point for the tree."""
    from genealogy.models import Person

    index = index or FamilyIndex.load()
    founders = [pid for pid in index.children if not index.parents.get(pid)]
    if not founders:
        return Person.objects.order_by("pk").values_list("pk", flat=True).first()
    return max(founders, key=lambda pid: (len(descendants(pid, index)), -pid))


# ---------------------------------------------------------------------------
# Kinship naming
# ---------------------------------------------------------------------------
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth"}
REMOVED = {1: "once", 2: "twice"}


def _gendered(gender, male, female, neutral):
    return male if gender == "M" else female if gender == "F" else neutral


def kinship_label(up, down, gender="U", half=False):
    """Name what B is to A.

    ``up`` is the number of generations from A to the closest common ancestor,
    ``down`` the number from B to that ancestor. ``gender`` is B's gender.
    """
    half_prefix = "half-" if half else ""
    if up == 0 and down == 0:
        return "self"
    if down == 0:  # B is A's ancestor
        if up == 1:
            return _gendered(gender, "father", "mother", "parent")
        return "great-" * (up - 2) + _gendered(gender, "grandfather", "grandmother", "grandparent")
    if up == 0:  # B is A's descendant
        if down == 1:
            return _gendered(gender, "son", "daughter", "child")
        return "great-" * (down - 2) + _gendered(gender, "grandson", "granddaughter", "grandchild")
    if up == 1 and down == 1:
        return half_prefix + _gendered(gender, "brother", "sister", "sibling")
    if up == 1:  # B descends from A's sibling
        word = _gendered(gender, "nephew", "niece", "nephew/niece")
        if down == 2:
            return half_prefix + word
        return half_prefix + "great-" * (down - 3) + "grand" + word
    if down == 1:  # B is a sibling of A's ancestor
        return half_prefix + "great-" * (up - 2) + _gendered(gender, "uncle", "aunt", "uncle/aunt")
    degree = min(up, down) - 1
    removed = abs(up - down)
    label = f"{ORDINALS.get(degree, f'{degree}th')} cousin"
    if removed:
        label += f" {REMOVED.get(removed, f'{removed} times')} removed"
    return label


@dataclass
class Relationship:
    label: str | None
    kind: str  # "self", "blood", "spouse", "in-law" or "none"
    path: list = field(default_factory=list)
    common_ancestors: list = field(default_factory=list)
    up: int | None = None
    down: int | None = None
    half: bool = False

    @property
    def found(self):
        return self.kind != "none"


def _is_half(a_id, b_id, index):
    shared = index.parents.get(a_id, set()) & index.parents.get(b_id, set())
    only_a = index.parents.get(a_id, set()) - shared
    only_b = index.parents.get(b_id, set()) - shared
    # Only call it "half" when both sides record a parent the other doesn't have.
    return len(shared) == 1 and bool(only_a) and bool(only_b)


def _chain(walk, node):
    """Follow ``previous`` pointers from ``node`` back to the walk's origin."""
    chain = []
    while node is not None:
        chain.append(node)
        node = walk[node][1]
    return chain


def _blood_relationship(a_id, b_id, index, genders):
    up_a = _walk(a_id, index.parents)
    up_b = _walk(b_id, index.parents)
    common = set(up_a) & set(up_b)
    if not common:
        return None
    best = min(common, key=lambda c: (up_a[c][0] + up_b[c][0], up_a[c][0], c))
    up, down = up_a[best][0], up_b[best][0]
    closest = sorted(c for c in common if (up_a[c][0], up_b[c][0]) == (up, down))

    half = False
    if up >= 1 and down >= 1 and (up == 1 or down == 1):
        # Compare the two siblings directly below the common ancestor.
        side_a = up_a[best][1]
        side_b = up_b[best][1]
        half = _is_half(side_a, side_b, index)

    path = list(reversed(_chain(up_a, best))) + _chain(up_b, best)[1:]
    return Relationship(
        label=kinship_label(up, down, genders.get(b_id, "U"), half),
        kind="blood",
        path=path,
        common_ancestors=[c for c in closest if c not in (a_id, b_id)],
        up=up,
        down=down,
        half=half,
    )


def _in_law_via_spouse(rel, gender_b, gender_spouse):
    """B is a blood relative of A's spouse; ``rel`` is spouse → B."""
    if (rel.up, rel.down) == (1, 0):
        return _gendered(gender_b, "father-in-law", "mother-in-law", "parent-in-law")
    if (rel.up, rel.down) == (1, 1):
        return _gendered(gender_b, "brother-in-law", "sister-in-law", "sibling-in-law")
    if (rel.up, rel.down) == (0, 1):
        return _gendered(gender_b, "stepson", "stepdaughter", "stepchild")
    return f"{_gendered(gender_spouse, 'husband', 'wife', 'spouse')}'s {rel.label}"


def _in_law_via_relative(rel, gender_b):
    """B is the spouse of A's blood relative; ``rel`` is A → that relative."""
    if (rel.up, rel.down) == (0, 1):
        return _gendered(gender_b, "son-in-law", "daughter-in-law", "child-in-law")
    if (rel.up, rel.down) == (1, 1):
        return _gendered(gender_b, "brother-in-law", "sister-in-law", "sibling-in-law")
    if (rel.up, rel.down) == (1, 0):
        return _gendered(gender_b, "stepfather", "stepmother", "step-parent")
    return f"{rel.label}'s {_gendered(gender_b, 'husband', 'wife', 'spouse')}"


def relationship_between(a, b, index=None):
    """Describe what person ``b`` is to person ``a``."""
    from genealogy.models import Person

    index = index or FamilyIndex.load()
    a_id, b_id = _pk(a), _pk(b)
    if a_id == b_id:
        return Relationship("self", "self", [a_id])

    genders = dict(Person.objects.values_list("pk", "gender"))

    blood = _blood_relationship(a_id, b_id, index, genders)
    if blood:
        return blood

    if b_id in index.partners.get(a_id, ()):
        return Relationship(_gendered(genders.get(b_id), "husband", "wife", "spouse"), "spouse", [a_id, b_id])

    for spouse_id in sorted(index.partners.get(a_id, ())):
        rel = _blood_relationship(spouse_id, b_id, index, genders)
        if rel:
            label = _in_law_via_spouse(rel, genders.get(b_id), genders.get(spouse_id))
            return Relationship(label, "in-law", [a_id, *rel.path], rel.common_ancestors, rel.up, rel.down)

    for spouse_id in sorted(index.partners.get(b_id, ())):
        rel = _blood_relationship(a_id, spouse_id, index, genders)
        if rel:
            label = _in_law_via_relative(rel, genders.get(b_id))
            return Relationship(label, "in-law", [*rel.path, b_id], rel.common_ancestors, rel.up, rel.down)

    return Relationship(None, "none")


def describe(rel, a, b):
    """A sentence such as “Victor Karanja is John Ngigi's brother.”"""
    if rel.kind == "self":
        return f"That's the same person: {a.display_name}."
    if not rel.found:
        return f"No relationship between {a.display_name} and {b.display_name} is recorded yet."
    return f"{b.display_name} is {a.display_name}'s {rel.label}."


# ---------------------------------------------------------------------------
# Tree data for the Cytoscape front end
# ---------------------------------------------------------------------------
def person_summary(person, hide_living_birth=False):
    data = {
        "pk": person.pk,
        "name": person.full_name,
        "label": person.display_name,
        "lifespan": person.lifespan_text(hide_living_birth),
        "gender": person.gender,
        "living": person.is_living,
        "lineage": person.lineage,
        "initials": person.initials,
        "url": person.get_absolute_url(),
    }
    if person.photo:
        data["photo"] = person.photo.url
    return data


def build_graph(root=None, up=3, down=3, hide_living_birth=False):
    """Cytoscape elements for the whole family, or a window around ``root``.

    Couples are joined through a small "union" node, with edges running
    partner → union → child, so a layered layout keeps each generation on its
    own row.
    """
    from django.db.models import Q

    from genealogy.models import ParentChild, Person, Union, marital_status_for

    index = FamilyIndex.load()
    root_id = _pk(root) if root is not None else None

    people_qs = Person.objects.all()
    if root_id is not None:
        ids = {root_id}
        ids |= set(ancestors(root_id, index, limit=up))
        ids |= set(descendants(root_id, index, limit=down))
        for parent_id in index.parents.get(root_id, ()):
            ids |= index.children.get(parent_id, set())  # siblings
        for pid in list(ids):
            ids |= index.partners.get(pid, set())
        people_qs = people_qs.filter(pk__in=ids)

    people = list(people_qs.select_related("homeland", "named_after").prefetch_related("tags"))
    included = {p.pk for p in people}
    generations = generation_numbers(index)
    birth_orders = birth_order_labels(included, index)
    unions_by_person = defaultdict(list)
    for union in Union.objects.filter(Q(partner_a_id__in=included) | Q(partner_b_id__in=included)):
        for pid in (union.partner_a_id, union.partner_b_id):
            if pid in included:
                unions_by_person[pid].append(union)
    elements = []
    edge_ids = set()

    def add_edge(source, target, **data):
        edge_id = f"e-{source}-{target}"
        if edge_id not in edge_ids:
            edge_ids.add(edge_id)
            elements.append({"group": "edges", "data": {"id": edge_id, "source": source, "target": target, **data}})

    for person in people:
        data = person_summary(person, hide_living_birth)
        data.update(
            {
                "id": f"p{person.pk}",
                "kind": "person",
                "root": person.pk == root_id,
                "generation": generations.get(person.pk, 1),
                "birthOrder": birth_orders.get(person.pk, ""),
                "children": len(index.children.get(person.pk, ())),
                "tags": [tag.name for tag in person.tags.all()],
                "namedAfter": person.named_after.display_name if person.named_after else "",
                "homeland": person.homeland.name if person.homeland else "",
                "marital": marital_status_for(unions_by_person[person.pk], person),
                "gaps": len(person.record_gaps()),
            }
        )
        elements.append({"group": "nodes", "data": data})

    unions = {}
    for union in Union.objects.filter(partner_a_id__in=included):
        partner_ids = {union.partner_a_id, union.partner_b_id} - {None}
        if not partner_ids <= included:
            continue
        unions[union.pk] = union
        node_id = f"u{union.pk}"
        elements.append(
            {
                "group": "nodes",
                "data": {"id": node_id, "kind": "union", "type": union.union_type, "current": union.is_current},
            }
        )
        for pid in sorted(partner_ids):
            add_edge(f"p{pid}", node_id, kind="partner")

    union_by_pair = {
        frozenset((u.partner_a_id, u.partner_b_id)): u.pk for u in unions.values() if u.partner_b_id
    }

    links_by_child = defaultdict(list)
    link_qs = ParentChild.objects.filter(child_id__in=included, parent_id__in=included)
    for link in link_qs.values("parent_id", "child_id", "union_id", "relationship_type").order_by("pk"):
        links_by_child[link["child_id"]].append(link)

    for child_id, links in links_by_child.items():
        parent_ids = {link["parent_id"] for link in links}
        covered = set()
        for link in links:
            parent_id = link["parent_id"]
            if parent_id in covered:
                continue
            union_id = link["union_id"] if link["union_id"] in unions else None
            if union_id is None:
                union_id = next(
                    (
                        union_by_pair[frozenset((parent_id, other))]
                        for other in sorted(parent_ids - {parent_id})
                        if frozenset((parent_id, other)) in union_by_pair
                    ),
                    None,
                )
            if union_id is not None:
                union = unions[union_id]
                covered |= {union.partner_a_id, union.partner_b_id}
                add_edge(f"u{union_id}", f"p{child_id}", kind="child", rtype=link["relationship_type"])
            else:
                covered.add(parent_id)
                add_edge(f"p{parent_id}", f"p{child_id}", kind="child", rtype=link["relationship_type"])

    return {"elements": elements, "root": root_id, "count": len(people)}
