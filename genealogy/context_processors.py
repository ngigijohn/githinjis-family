from django.conf import settings

NAV_ITEMS = [
    {"section": "tree", "label": "Family tree", "url_name": "genealogy:tree"},
    {"section": "people", "label": "People", "url_name": "genealogy:person_list"},
    {"section": "places", "label": "Places", "url_name": "genealogy:place_list"},
    {"section": "gallery", "label": "Memories", "url_name": "gallery:photo_list"},
    {"section": "relationship", "label": "How are we related?", "url_name": "genealogy:relationship"},
    {"section": "about", "label": "About", "url_name": "genealogy:about"},
]
DASHBOARD_ITEM = {"section": "dashboard", "label": "Dashboard", "url_name": "genealogy:dashboard"}

SECTIONS = {
    "home": "home",
    "dashboard": "dashboard",
    "tree": "tree",
    "person_list": "people",
    "person_detail": "people",
    "person_add": "people",
    "person_edit": "people",
    "person_delete": "people",
    "tag_list": "people",
    "tag_detail": "people",
    "bookmarks": "people",
    "place_list": "places",
    "place_detail": "places",
    "relationship": "relationship",
    "photo_list": "gallery",
    "photo_add": "gallery",
    "photo_edit": "gallery",
    "photo_delete": "gallery",
    "recording_list": "gallery",
    "recording_detail": "gallery",
    "recording_add": "gallery",
    "recording_edit": "gallery",
    "recording_delete": "gallery",
    "about": "about",
    "contact": "contact",
}


def site(request):
    match = getattr(request, "resolver_match", None)
    items = NAV_ITEMS
    if getattr(request.user, "is_authenticated", False):
        items = [DASHBOARD_ITEM] + NAV_ITEMS
    return {
        "SITE_NAME": settings.SITE_NAME,
        "nav_items": items,
        "nav_section": SECTIONS.get(match.url_name) if match else None,
    }
