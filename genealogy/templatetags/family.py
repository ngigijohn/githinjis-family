from django import template

from genealogy.models import Place, Tag

register = template.Library()

AVATAR_SIZES = {
    "sm": "h-8 w-8 text-xs",
    "md": "h-12 w-12 text-sm",
    "lg": "h-20 w-20 text-xl",
    "xl": "h-32 w-32 text-3xl sm:h-40 sm:w-40",
}
AVATAR_TONES = {
    "M": "bg-male-soft text-male",
    "F": "bg-rose-soft text-rose",
}
AVATAR_NEUTRAL_TONE = "bg-line/70 text-muted"


@register.filter
def lifespan_for(person, user):
    """Lifespan that hides living people's birth years from anonymous visitors."""
    return person.lifespan_text(hide_living_birth=not getattr(user, "is_authenticated", False))


@register.filter
def natural_join(items, conjunction="and"):
    """``["a", "b", "c"]`` → ``"a, b and c"``."""
    items = [str(item) for item in items]
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


@register.inclusion_tag("includes/avatar.html")
def avatar(person, size="md"):
    return {
        "person": person,
        "size_class": AVATAR_SIZES.get(size, AVATAR_SIZES["md"]),
        "tone": AVATAR_TONES.get(person.gender, AVATAR_NEUTRAL_TONE),
    }


@register.inclusion_tag("includes/datalists.html")
def form_datalists():
    """Suggestions for the place and tag text boxes in editing forms."""
    return {
        "places": Place.objects.select_related("parent__parent__parent"),
        "tags": Tag.objects.all(),
    }


@register.simple_tag(takes_context=True)
def query_with(context, **kwargs):
    """Current query string with some parameters replaced (used for pagination)."""
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        params[key] = value
    return params.urlencode()
