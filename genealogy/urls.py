from django.urls import path

from . import api, views

app_name = "genealogy"

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("tree/", views.tree, name="tree"),
    path("people/", views.PersonListView.as_view(), name="person_list"),
    path("people/add/", views.PersonCreateView.as_view(), name="person_add"),
    path("people/<int:pk>/", views.PersonDetailView.as_view(), name="person_detail"),
    path("people/<int:pk>/edit/", views.PersonUpdateView.as_view(), name="person_edit"),
    path("people/<int:pk>/delete/", views.PersonDeleteView.as_view(), name="person_delete"),
    path("people/<int:pk>/link/", views.person_link, name="person_link"),
    path("people/<int:pk>/unlink/", views.person_unlink, name="person_unlink"),
    path("people/<int:pk>/events/add/", views.event_add, name="event_add"),
    path("people/<int:pk>/history/<str:kind>/add/", views.history_add, name="history_add"),
    path("people/<int:pk>/bookmark/", views.bookmark_toggle, name="bookmark_toggle"),
    path("events/<int:pk>/delete/", views.event_delete, name="event_delete"),
    path("history/<str:kind>/<int:pk>/delete/", views.history_delete, name="history_delete"),
    path("bookmarks/", views.bookmarks, name="bookmarks"),
    path("places/", views.place_list, name="place_list"),
    path("places/<int:pk>/", views.place_detail, name="place_detail"),
    path("tags/", views.tag_list, name="tag_list"),
    path("tags/<slug:slug>/", views.tag_detail, name="tag_detail"),
    path("relationship/", views.relationship, name="relationship"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("api/tree/", api.tree_data, name="api_tree"),
    path("api/people/search/", api.people_search, name="api_people_search"),
    path("api/relationship/", api.relationship_data, name="api_relationship"),
]
