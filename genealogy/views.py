from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from gallery.models import Photo, Recording

from .forms import (
    ContactForm,
    EducationForm,
    EmploymentForm,
    LifeEventForm,
    LinkRelativeForm,
    PersonCreateForm,
    PersonForm,
    ResidenceForm,
)
from .models import Bookmark, Education, Employment, LifeEvent, ParentChild, Person, Place, Residence, Tag, Union
from .services.relations import (
    FamilyIndex,
    build_graph,
    describe,
    generation_count,
    generation_numbers,
    relationship_between,
    suggested_root,
)
from .templatetags.family import natural_join

TREE_SHOW_ALL_LIMIT = 150

# kind in the URL -> (model, form, column title, add-button label, empty message)
HISTORY = {
    "home": (Residence, ResidenceForm, "Homes", "Add a home", "No homes recorded yet."),
    "education": (Education, EducationForm, "Education", "Add a school", "No schools recorded yet."),
    "work": (Employment, EmploymentForm, "Work", "Add work", "No work recorded yet."),
}


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def home(request):
    people_count = Person.objects.count()
    context = {
        "people_count": people_count,
        "generation_count": generation_count(FamilyIndex.load()) or (1 if people_count else 0),
        "family_count": Union.objects.count(),
        "photo_count": Photo.objects.count(),
        "recent_people": Person.objects.order_by("-created_at")[:8],
        "recent_photos": Photo.objects.all()[:8],
    }
    return render(request, "genealogy/home.html", context)


def tree(request):
    root = Person.objects.filter(pk=_int_or_none(request.GET.get("root"))).first()
    people_count = Person.objects.count()
    suggested = None
    if not root and people_count > TREE_SHOW_ALL_LIMIT:
        suggested = Person.objects.filter(pk=suggested_root()).first()
    focus = root or suggested
    fallback = focus or Person.objects.filter(pk=suggested_root()).first()
    config = {
        "endpoint": reverse("genealogy:api_tree"),
        "searchEndpoint": reverse("genealogy:api_people_search"),
        "rootId": focus.pk if focus else None,
        "rootName": focus.full_name if focus else "",
        "defaultRootId": fallback.pk if fallback else None,
        "defaultRootName": fallback.full_name if fallback else "",
        "up": max(0, min(_int_or_none(request.GET.get("up")) or 3, 10)),
        "down": max(0, min(_int_or_none(request.GET.get("down")) or 3, 10)),
        "canEdit": request.user.has_perm("genealogy.add_person"),
        "layout": "network" if request.GET.get("layout") == "network" else "tree",
    }
    return render(request, "genealogy/tree.html", {"config": config, "people_count": people_count})


@login_required
def dashboard(request):
    """An overview for signed-in relatives: today's anniversaries, gaps in the records and recent additions."""
    from datetime import date

    today = date.today()

    def next_anniversary(day):
        """The next anniversary of ``day`` and how many days away it is."""
        for year in (today.year, today.year + 1):
            try:
                when = day.replace(year=year)
            except ValueError:  # 29 February in a year that has none
                when = day.replace(year=year, day=28)
            if when >= today:
                return when, (when - today).days
        return day, 0

    on_this_day = [
        {"person": person, "what": "was born", "years": today.year - person.birth_date.year}
        for person in Person.objects.filter(birth_date__month=today.month, birth_date__day=today.day).exclude(birth_date__year=today.year)
    ] + [
        {"person": person, "what": "died", "years": today.year - person.death_date.year}
        for person in Person.objects.filter(death_date__month=today.month, death_date__day=today.day)
    ]
    weddings = [
        {"union": union, "years": today.year - union.start_date.year}
        for union in Union.objects.filter(start_date__month=today.month, start_date__day=today.day).select_related("partner_a", "partner_b")
    ]

    upcoming = []
    for person in Person.objects.filter(is_living=True).exclude(birth_date=None):
        when, days = next_anniversary(person.birth_date)
        if 0 < days <= 30:
            upcoming.append({"person": person, "when": when, "days": days, "turning": when.year - person.birth_date.year})
    upcoming.sort(key=lambda row: row["days"])

    _, places_by_pk = place_tree()
    busiest = sorted(
        (node for node in places_by_pk.values() if node["place"].kind != Place.Kind.COUNTRY and node["count"]),
        key=lambda node: (-node["count"], node["place"].name),
    )[:6]

    people = Person.objects.count()
    context = {
        "counts": {
            "people": people,
            "generations": generation_count(FamilyIndex.load()),
            "couples": Union.objects.count(),
            "places": Place.objects.count(),
            "photos": Photo.objects.count(),
            "recordings": Recording.objects.count(),
            "stories": Person.objects.exclude(biography="").count(),
        },
        "on_this_day": on_this_day,
        "weddings": weddings,
        "upcoming": upcoming[:6],
        "gaps": [
            {"label": "no birth date", "count": Person.objects.filter(birth_date=None).count()},
            {"label": "no birthplace", "count": Person.objects.filter(birth_place=None).count()},
            {"label": "no photo", "count": Person.objects.filter(photo="").count()},
            {"label": "no story written", "count": Person.objects.exclude(biography__gt="").count()},
            {"label": "flagged for review", "count": Person.objects.filter(needs_review=True).count()},
        ],
        "busiest_places": busiest,
        "recent_people": Person.objects.order_by("-created_at")[:6],
        "recent_photos": Photo.objects.all()[:6],
        "recent_recordings": Recording.objects.all()[:3],
        "total_people": people,
    }
    return render(request, "genealogy/dashboard.html", context)


def place_connections():
    """``{place_id: {person_id, ...}}``: everyone connected directly to each place."""
    links = defaultdict(set)
    for field in ("birth_place", "death_place", "homeland"):
        for person_id, place_id in Person.objects.exclude(**{field: None}).values_list("pk", f"{field}_id"):
            links[place_id].add(person_id)
    for model in (Residence, Education, Employment):
        for person_id, place_id in model.objects.exclude(place=None).values_list("person_id", "place_id"):
            links[place_id].add(person_id)
    return links


def place_tree(links=None):
    """Nested ``{"place", "children", "count"}`` nodes, counting people in a place or anywhere inside it."""
    links = place_connections() if links is None else links
    places = list(Place.objects.select_related("parent"))
    children = defaultdict(list)
    for place in places:
        children[place.parent_id].append(place)
    by_pk = {}

    def build(place, seen):
        seen = seen | {place.pk}
        kids = [build(child, seen) for child in children[place.pk] if child.pk not in seen]
        people = set(links.get(place.pk, ()))
        for kid in kids:
            people |= kid["people"]
        kids.sort(key=lambda node: (-node["count"], node["place"].name))
        node = {"place": place, "children": kids, "people": people, "count": len(people)}
        by_pk[place.pk] = node
        return node

    roots = sorted((build(place, set()) for place in children[None]), key=lambda node: (-node["count"], node["place"].name))
    return roots, by_pk


class PersonListView(ListView):
    model = Person
    paginate_by = 24
    template_name = "genealogy/person_list.html"
    context_object_name = "people"

    SORTS = {
        "name": ["last_name", "first_name"],
        "oldest": ["birth_date", "last_name"],
        "youngest": ["-birth_date", "last_name"],
        "recent": ["-created_at"],
    }

    def selected_place(self):
        pk = _int_or_none(self.request.GET.get("place"))
        return Place.objects.select_related("parent").filter(pk=pk).first() if pk else None

    def get_queryset(self):
        params = self.request.GET
        qs = Person.objects.search(params.get("q", "")).prefetch_related("tags")
        if params.get("surname"):
            qs = qs.filter(last_name__iexact=params["surname"])
        if params.get("lineage"):
            qs = qs.filter(lineage__iexact=params["lineage"])
        if params.get("tag"):
            qs = qs.filter(tags__slug=params["tag"])
        place = self.selected_place()
        if place:
            ids = place.descendant_ids()
            qs = qs.filter(
                Q(birth_place__in=ids)
                | Q(death_place__in=ids)
                | Q(homeland__in=ids)
                | Q(residences__place__in=ids)
                | Q(education__place__in=ids)
                | Q(employment__place__in=ids)
            )
        if params.get("status") == "living":
            qs = qs.filter(is_living=True)
        elif params.get("status") == "deceased":
            qs = qs.filter(is_living=False)
        return qs.distinct().order_by(*self.SORTS.get(params.get("sort"), self.SORTS["name"]))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        people = Person.objects.order_by()
        context.update(
            {
                "surnames": people.exclude(last_name="").values_list("last_name", flat=True).distinct().order_by("last_name"),
                "lineages": people.exclude(lineage="").values_list("lineage", flat=True).distinct().order_by("lineage"),
                "places": Place.objects.filter(pk__in=place_connections().keys()).select_related("parent").order_by("name"),
                "tags": Tag.objects.filter(people__isnull=False).distinct().order_by("name"),
                "selected_place": self.selected_place(),
                "filters": self.request.GET,
                "total_count": Person.objects.count(),
            }
        )
        return context


class PersonDetailView(DetailView):
    model = Person
    template_name = "genealogy/person_detail.html"
    context_object_name = "person"

    def get_queryset(self):
        return Person.objects.select_related("birth_place__parent", "death_place__parent", "homeland__parent", "named_after")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        user = self.request.user

        parent_links = list(person.parent_links.select_related("parent"))
        child_links = list(person.child_links.select_related("child"))
        unions = list(person.unions())

        # Group children under the union they belong to.
        child_ids = [link.child_id for link in child_links]
        other_parents = defaultdict(set)
        for child_id, parent_id in (
            ParentChild.objects.filter(child_id__in=child_ids).exclude(parent=person).values_list("child_id", "parent_id")
        ):
            other_parents[child_id].add(parent_id)
        partner_union = {u.other(person).pk: u.pk for u in unions if u.other(person)}
        children_by_union = defaultdict(list)
        for link in child_links:
            key = link.union_id
            if key is None:
                key = next((partner_union[p] for p in other_parents[link.child_id] if p in partner_union), None)
            children_by_union[key].append(link)

        families = [
            {"union": union, "partner": union.other(person), "children": children_by_union.pop(union.pk, [])}
            for union in unions
        ]
        other_children = [link for links in children_by_union.values() for link in links]

        # Siblings, flagged as half-siblings where each side has a parent the other lacks.
        my_parents = {link.parent_id for link in parent_links}
        sibling_parents = defaultdict(set)
        sibling_ids = ParentChild.objects.filter(parent_id__in=my_parents).exclude(child=person).values_list("child_id", flat=True)
        for child_id, parent_id in ParentChild.objects.filter(child_id__in=sibling_ids).values_list("child_id", "parent_id"):
            sibling_parents[child_id].add(parent_id)
        siblings = []
        for sibling in Person.objects.filter(pk__in=sibling_parents).order_by("birth_date", "first_name"):
            theirs = sibling_parents[sibling.pk]
            shared = my_parents & theirs
            siblings.append({"person": sibling, "half": len(shared) == 1 and bool(my_parents - shared) and bool(theirs - shared)})

        can_edit = user.has_perm("genealogy.change_person")
        show_private = user.is_authenticated or not person.is_living
        gaps = person.record_gaps()
        context.update(
            {
                "parent_links": parent_links,
                "families": families,
                "other_children": other_children,
                "siblings": siblings,
                "events": person.events.select_related("place__parent"),
                "photos": person.photos.all()[:12],
                "recordings": Recording.objects.filter(Q(speakers=person) | Q(people=person)).distinct(),
                "history": self.history(person, show_private, can_edit),
                "current_home": person.residences.filter(is_current=True).select_related("place__parent").first(),
                "namesakes": person.namesakes.all(),
                "tags": person.tags.all(),
                "summary": [part for part in (person.birth_order_label, person.marital_status) if part],
                "gaps": gaps,
                "gaps_text": natural_join(gaps),
                "is_bookmarked": user.is_authenticated and Bookmark.objects.filter(user=user, person=person).exists(),
                "show_private": show_private,
                "can_edit": can_edit,
                "can_delete": user.has_perm("genealogy.delete_person"),
                "link_form": LinkRelativeForm(person=person) if can_edit else None,
                "event_form": LifeEventForm() if can_edit else None,
            }
        )
        return context

    @staticmethod
    def history(person, show_private, can_edit):
        columns = []
        for kind, (model, form_class, title, add_label, empty) in HISTORY.items():
            rows = []
            for item in model.objects.filter(person=person).select_related("place__parent"):
                current = getattr(item, "is_current", False)
                row = {"pk": item.pk, "place": item.place, "years": item.years, "secondary": "", "current": ""}
                if kind == "home":
                    if current and person.is_living and not show_private:
                        row.update(primary="Current home", place=None, years="Private. Sign in to see.")
                    else:
                        row.update(primary=item.place.name, secondary=item.notes, current="Current home" if current else "")
                elif kind == "education":
                    detail = item.get_level_display() if item.level != Education.Level.OTHER else ""
                    row.update(primary=item.institution, secondary=" · ".join(filter(None, [detail, item.field_of_study])))
                else:
                    row.update(
                        primary=f"{item.role} at {item.employer}" if item.role else item.employer,
                        secondary=item.notes,
                        current="Works here now" if current else "",
                    )
                rows.append(row)
            columns.append(
                {
                    "kind": kind,
                    "title": title,
                    "add_label": add_label,
                    "empty": empty,
                    "rows": rows,
                    "form": form_class(prefix=kind) if can_edit else None,
                }
            )
        return columns


class PersonCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "genealogy.add_person"
    form_class = PersonCreateForm
    template_name = "genealogy/person_form.html"

    def get_relative(self):
        pk = _int_or_none(self.request.POST.get("of") or self.request.GET.get("of"))
        return Person.objects.filter(pk=pk).first() if pk else None

    def get_initial(self):
        initial = super().get_initial()
        relation = self.request.GET.get("relation")
        if relation in {"child", "parent", "partner"}:
            initial["relation"] = relation
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["relative"] = self.get_relative()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relative"] = self.get_relative()
        return context

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        with transaction.atomic():
            response = super().form_valid(form)
            form.save_relationship(self.object)
        messages.success(self.request, f"{self.object.full_name} was added to the family.")
        return response


class PersonUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "genealogy.change_person"
    model = Person
    form_class = PersonForm
    template_name = "genealogy/person_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)


class PersonDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = "genealogy.delete_person"
    model = Person
    template_name = "genealogy/person_confirm_delete.html"
    success_url = reverse_lazy("genealogy:person_list")

    def form_valid(self, form):
        messages.success(self.request, f"{self.object.full_name} was removed from the family records.")
        return super().form_valid(form)


@require_POST
@permission_required("genealogy.change_person", raise_exception=True)
def person_link(request, pk):
    person = get_object_or_404(Person, pk=pk)
    form = LinkRelativeForm(request.POST, person=person)
    if form.is_valid():
        form.save()
        messages.success(request, "Relationship added.")
    else:
        errors = [error for field_errors in form.errors.values() for error in field_errors]
        messages.error(request, " ".join(errors) or "That relationship could not be added.")
    return redirect(person)


@require_POST
@permission_required("genealogy.change_person", raise_exception=True)
def person_unlink(request, pk):
    person = get_object_or_404(Person, pk=pk)
    kind, link_id = request.POST.get("kind"), _int_or_none(request.POST.get("id"))
    if kind == "parentchild":
        link = get_object_or_404(ParentChild, pk=link_id)
        involved = {link.parent_id, link.child_id}
    elif kind == "union":
        link = get_object_or_404(Union, pk=link_id)
        involved = {link.partner_a_id, link.partner_b_id}
    else:
        messages.error(request, "Unknown relationship type.")
        return redirect(person)
    if person.pk not in involved:
        messages.error(request, "That relationship does not belong to this person.")
    else:
        link.delete()
        messages.success(request, "Relationship removed.")
    return redirect(person)


@require_POST
@permission_required("genealogy.change_person", raise_exception=True)
def event_add(request, pk):
    person = get_object_or_404(Person, pk=pk)
    form = LifeEventForm(request.POST)
    if form.is_valid():
        event = form.save(commit=False)
        event.person = person
        event.save()
        messages.success(request, "Life event added to the timeline.")
    else:
        messages.error(request, "Please check the life event details and try again.")
    return redirect(f"{person.get_absolute_url()}#timeline")


@require_POST
@permission_required("genealogy.delete_lifeevent", raise_exception=True)
def event_delete(request, pk):
    event = get_object_or_404(LifeEvent, pk=pk)
    person = event.person
    event.delete()
    messages.success(request, "Life event removed.")
    return redirect(f"{person.get_absolute_url()}#timeline")


@require_POST
@permission_required("genealogy.change_person", raise_exception=True)
def history_add(request, pk, kind):
    if kind not in HISTORY:
        raise Http404("Unknown kind of life history.")
    person = get_object_or_404(Person, pk=pk)
    model, form_class, title, *_ = HISTORY[kind]
    form = form_class(request.POST, prefix=kind)
    if form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            item.person = person
            item.save()
            if getattr(item, "is_current", False):
                model.objects.filter(person=person, is_current=True).exclude(pk=item.pk).update(is_current=False)
        messages.success(request, f"Added to {person.first_name}'s {title.lower()}.")
    else:
        errors = [error for field_errors in form.errors.values() for error in field_errors]
        messages.error(request, " ".join(errors) or "Please check the details and try again.")
    return redirect(f"{person.get_absolute_url()}#life")


@require_POST
@permission_required("genealogy.change_person", raise_exception=True)
def history_delete(request, kind, pk):
    if kind not in HISTORY:
        raise Http404("Unknown kind of life history.")
    item = get_object_or_404(HISTORY[kind][0], pk=pk)
    person = item.person
    item.delete()
    messages.success(request, "Removed.")
    return redirect(f"{person.get_absolute_url()}#life")


@require_POST
@login_required
def bookmark_toggle(request, pk):
    person = get_object_or_404(Person, pk=pk)
    bookmark, created = Bookmark.objects.get_or_create(user=request.user, person=person)
    if created:
        messages.success(request, f"{person.first_name} was added to your bookmarks.")
    else:
        bookmark.delete()
        messages.success(request, f"{person.first_name} was removed from your bookmarks.")
    return redirect(person)


@login_required
def bookmarks(request):
    people = Person.objects.filter(bookmarked_by__user=request.user).prefetch_related("tags").order_by("-bookmarked_by__created_at")
    return render(request, "genealogy/bookmarks.html", {"people": people})


def place_list(request):
    nodes, by_pk = place_tree()
    countries = [node for node in nodes if node["place"].kind == Place.Kind.COUNTRY and node["count"]]
    home_country = countries[0] if countries else None
    busiest = sorted(
        (node for node in by_pk.values() if node["place"].kind != Place.Kind.COUNTRY and node["count"]),
        key=lambda node: (-node["count"], node["place"].name),
    )[:8]
    context = {
        "nodes": nodes,
        "busiest": busiest,
        "abroad": [node for node in countries if node is not home_country],
        "place_count": len(by_pk),
    }
    return render(request, "genealogy/place_list.html", context)


def place_detail(request, pk):
    place = get_object_or_404(Place.objects.select_related("parent"), pk=pk)
    ids = place.descendant_ids()
    signed_in = request.user.is_authenticated

    def where(item_place):
        return "" if item_place is None or item_place.pk == place.pk else f"in {item_place.name}"

    def details(*parts):
        return " · ".join(part for part in parts if part)

    people = Person.objects.select_related("birth_place", "death_place", "homeland")
    groups = []

    def add(title, rows):
        if rows:
            groups.append({"title": title, "rows": rows})

    add("Born here", [
        {"person": p, "detail": details(p.lifespan_text(hide_living_birth=not signed_in), where(p.birth_place))}
        for p in people.filter(birth_place__in=ids).order_by("birth_date", "first_name")
    ])
    add("Lived here", [
        {"person": r.person, "detail": details("Lives here now" if r.is_current else r.years, where(r.place))}
        for r in Residence.objects.filter(place__in=ids).select_related("person", "place")
        if signed_in or not (r.is_current and r.person.is_living)
    ])
    add("Studied here", [
        {"person": e.person, "detail": details(e.institution, e.years, where(e.place))}
        for e in Education.objects.filter(place__in=ids).select_related("person", "place")
    ])
    add("Worked here", [
        {"person": e.person, "detail": details(f"{e.role} at {e.employer}" if e.role else e.employer, e.years, where(e.place))}
        for e in Employment.objects.filter(place__in=ids).select_related("person", "place")
    ])
    add("Ancestral home of", [{"person": p, "detail": where(p.homeland)} for p in people.filter(homeland__in=ids)])
    add("Died here", [
        {"person": p, "detail": details(p.lifespan, where(p.death_place))} for p in people.filter(death_place__in=ids)
    ])

    _, by_pk = place_tree()
    children = [by_pk[child.pk] for child in place.children.all() if child.pk in by_pk]
    children.sort(key=lambda node: (-node["count"], node["place"].name))
    map_url = ""
    if place.latitude is not None and place.longitude is not None:
        map_url = f"https://www.openstreetmap.org/?mlat={place.latitude}&mlon={place.longitude}#map=11/{place.latitude}/{place.longitude}"
    context = {
        "place": place,
        "parents": list(reversed(place.hierarchy()[1:])),
        "children": children,
        "groups": groups,
        "people_count": len({row["person"].pk for group in groups for row in group["rows"]}),
        "recordings": Recording.objects.filter(place__in=ids),
        "map_url": map_url,
    }
    return render(request, "genealogy/place_detail.html", context)


def timeline(request):
    """Every recorded event across the generations, on one scrollable timeline."""
    params = request.GET
    signed_in = request.user.is_authenticated
    generations = generation_numbers()
    kind = params.get("kind", "")
    person_id = _int_or_none(params.get("person"))
    place = Place.objects.select_related("parent").filter(pk=_int_or_none(params.get("place"))).first()
    place_ids = place.descendant_ids() if place else None
    generation = _int_or_none(params.get("generation"))

    entries = []

    def add(date_value, kind_key, label, person, place_value, detail=""):
        if not date_value:
            return
        if person_id and person.pk != person_id:
            return
        if generation and generations.get(person.pk) != generation:
            return
        if place_ids is not None and (place_value is None or place_value.pk not in place_ids):
            return
        if kind and kind != kind_key:
            return
        entries.append(
            {
                "date": date_value,
                "kind": kind_key,
                "label": label,
                "person": person,
                "place": place_value,
                "detail": detail,
                "generation": generations.get(person.pk),
            }
        )

    people = Person.objects.select_related("birth_place__parent", "death_place__parent")
    for person in people:
        # Birth years of living relatives stay private, so their births only appear to family.
        if person.birth_date and (signed_in or not person.is_living):
            add(person.birth_date, "birth", "was born", person, person.birth_place)
        if person.death_date:
            add(person.death_date, "death", "died", person, person.death_place)

    for union in Union.objects.filter(start_date__isnull=False).select_related("partner_a", "partner_b"):
        other = union.partner_b
        if other:
            add(union.start_date, "marriage", f"married {other.first_name}", union.partner_a, None, union.get_union_type_display())

    for event in LifeEvent.objects.exclude(date=None).select_related("person", "place__parent"):
        add(event.date, event.event_type, event.heading.lower(), event.person, event.place)

    entries.sort(key=lambda entry: entry["date"])
    decades = []
    for entry in entries:
        decade = entry["date"].year // 10 * 10
        if not decades or decades[-1]["decade"] != decade:
            decades.append({"decade": decade, "entries": []})
        decades[-1]["entries"].append(entry)

    kinds = [("birth", "Births"), ("marriage", "Marriages"), ("death", "Deaths")] + [
        (value, label) for value, label in LifeEvent.Type.choices if value not in {"birth", "marriage", "death"}
    ]
    context = {
        "decades": decades,
        "total": len(entries),
        "kinds": kinds,
        "generations": sorted({g for g in generations.values()}),
        "places": Place.objects.filter(pk__in=place_connections().keys()).select_related("parent").order_by("name"),
        "selected_place": place,
        "selected_person": Person.objects.filter(pk=person_id).first() if person_id else None,
        "filters": params,
        "span": (entries[0]["date"].year, entries[-1]["date"].year) if entries else None,
    }
    return render(request, "genealogy/timeline.html", context)


def place_map(request):
    """The family on a map: where people were born, lived, studied, worked and are buried."""
    mapped = Place.objects.exclude(latitude=None).exclude(longitude=None).count()
    context = {
        "mapped_count": mapped,
        "unmapped_count": Place.objects.filter(latitude=None).count(),
        "config": {
            "placesEndpoint": reverse("genealogy:api_places"),
            "journeyEndpoint": reverse("genealogy:api_journey"),
            "searchEndpoint": reverse("genealogy:api_people_search"),
        },
    }
    return render(request, "genealogy/place_map.html", context)


def tag_list(request):
    tags = Tag.objects.annotate(people_count=Count("people")).filter(people_count__gt=0).order_by("name")
    by_category = defaultdict(list)
    for tag in tags:
        by_category[tag.category].append(tag)
    categories = [{"label": label, "tags": by_category[value]} for value, label in Tag.Category.choices if by_category[value]]
    return render(request, "genealogy/tag_list.html", {"categories": categories})


def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    people = tag.people.prefetch_related("tags").order_by("last_name", "first_name")
    return render(request, "genealogy/tag_detail.html", {"tag": tag, "people": people})


def relationship(request):
    a = Person.objects.filter(pk=_int_or_none(request.GET.get("a"))).first()
    b = Person.objects.filter(pk=_int_or_none(request.GET.get("b"))).first()
    result = None
    if a and b:
        rel = relationship_between(a, b)
        people = Person.objects.in_bulk(set(rel.path) | set(rel.common_ancestors))
        result = {
            "rel": rel,
            "sentence": describe(rel, a, b),
            "path": [people[pid] for pid in rel.path if pid in people],
            "common_ancestors": [people[pid] for pid in rel.common_ancestors if pid in people],
        }
    return render(request, "genealogy/relationship.html", {"a": a, "b": b, "result": result})


def about(request):
    stats = {
        "people": Person.objects.count(),
        "lineages": Person.objects.exclude(lineage="").values("lineage").annotate(n=Count("pk")).count(),
    }
    return render(request, "genealogy/about.html", {"stats": stats})


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thank you! Your message has been sent to the family administrators.")
        return redirect("genealogy:contact")
    return render(request, "genealogy/contact.html", {"form": form})
