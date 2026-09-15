from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from gallery.models import Photo

from .forms import ContactForm, LifeEventForm, LinkRelativeForm, PersonCreateForm, PersonForm
from .models import LifeEvent, ParentChild, Person, Union
from .services.relations import (
    FamilyIndex,
    build_graph,
    describe,
    generation_count,
    relationship_between,
    suggested_root,
)

TREE_SHOW_ALL_LIMIT = 150


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
    }
    return render(request, "genealogy/tree.html", {"config": config, "people_count": people_count})


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

    def get_queryset(self):
        params = self.request.GET
        qs = Person.objects.search(params.get("q", ""))
        if params.get("surname"):
            qs = qs.filter(last_name__iexact=params["surname"])
        if params.get("lineage"):
            qs = qs.filter(lineage__iexact=params["lineage"])
        if params.get("status") == "living":
            qs = qs.filter(is_living=True)
        elif params.get("status") == "deceased":
            qs = qs.filter(is_living=False)
        return qs.order_by(*self.SORTS.get(params.get("sort"), self.SORTS["name"]))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        people = Person.objects.order_by()
        context.update(
            {
                "surnames": people.exclude(last_name="").values_list("last_name", flat=True).distinct().order_by("last_name"),
                "lineages": people.exclude(lineage="").values_list("lineage", flat=True).distinct().order_by("lineage"),
                "filters": self.request.GET,
                "total_count": Person.objects.count(),
            }
        )
        return context


class PersonDetailView(DetailView):
    model = Person
    template_name = "genealogy/person_detail.html"
    context_object_name = "person"

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
        context.update(
            {
                "parent_links": parent_links,
                "families": families,
                "other_children": other_children,
                "siblings": siblings,
                "events": person.events.all(),
                "photos": person.photos.all()[:12],
                "show_private": user.is_authenticated or not person.is_living,
                "can_edit": can_edit,
                "can_delete": user.has_perm("genealogy.delete_person"),
                "link_form": LinkRelativeForm(person=person) if can_edit else None,
                "event_form": LifeEventForm() if can_edit else None,
            }
        )
        return context


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
