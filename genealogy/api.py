"""JSON endpoints used by the interactive tree and the person pickers."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Person
from .services.relations import build_graph, describe, person_summary, relationship_between


def _int(value, default=None, low=None, high=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None:
        number = max(low, number)
    if high is not None:
        number = min(high, number)
    return number


def _hide_private(request):
    return not request.user.is_authenticated


@require_GET
def tree_data(request):
    root_id = _int(request.GET.get("root"))
    if root_id is not None and not Person.objects.filter(pk=root_id).exists():
        return JsonResponse({"error": "Person not found."}, status=404)
    up = _int(request.GET.get("up"), 3, 0, 10)
    down = _int(request.GET.get("down"), 3, 0, 10)
    return JsonResponse(build_graph(root_id, up, down, hide_living_birth=_hide_private(request)))


@require_GET
def people_search(request):
    query = request.GET.get("q", "").strip()
    limit = _int(request.GET.get("limit"), 12, 1, 50)
    if not query:
        return JsonResponse({"results": []})
    people = Person.objects.search(query).order_by("first_name", "last_name")[:limit]
    hide = _hide_private(request)
    return JsonResponse({"results": [person_summary(p, hide) for p in people]})


@require_GET
def relationship_data(request):
    a = Person.objects.filter(pk=_int(request.GET.get("a"))).first()
    b = Person.objects.filter(pk=_int(request.GET.get("b"))).first()
    if not (a and b):
        return JsonResponse({"error": "Provide two valid people as ?a=<id>&b=<id>."}, status=400)
    rel = relationship_between(a, b)
    hide = _hide_private(request)
    people = Person.objects.in_bulk(set(rel.path) | set(rel.common_ancestors))
    return JsonResponse(
        {
            "label": rel.label,
            "kind": rel.kind,
            "sentence": describe(rel, a, b),
            "path": [person_summary(people[pid], hide) for pid in rel.path if pid in people],
            "common_ancestors": [person_summary(people[pid], hide) for pid in rel.common_ancestors if pid in people],
        }
    )
