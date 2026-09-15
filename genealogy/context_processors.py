from django.conf import settings

NAV_ITEMS = [
    {"section": "tree", "label": "Family tree", "url_name": "genealogy:tree"},
    {"section": "people", "label": "People", "url_name": "genealogy:person_list"},
    {"section": "relationship", "label": "How are we related?", "url_name": "genealogy:relationship"},
    {"section": "gallery", "label": "Gallery", "url_name": "gallery:photo_list"},
    {"section": "about", "label": "About", "url_name": "genealogy:about"},
]

SECTIONS = {
    "home": "home",
    "tree": "tree",
    "person_list": "people",
    "person_detail": "people",
    "person_add": "people",
    "person_edit": "people",
    "person_delete": "people",
    "relationship": "relationship",
    "photo_list": "gallery",
    "photo_add": "gallery",
    "photo_edit": "gallery",
    "photo_delete": "gallery",
    "about": "about",
    "contact": "contact",
}


def site(request):
    match = getattr(request, "resolver_match", None)
    return {
        "SITE_NAME": settings.SITE_NAME,
        "nav_items": NAV_ITEMS,
        "nav_section": SECTIONS.get(match.url_name) if match else None,
    }
