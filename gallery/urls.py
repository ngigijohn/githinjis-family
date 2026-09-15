from django.urls import path

from . import views

app_name = "gallery"

urlpatterns = [
    path("", views.PhotoListView.as_view(), name="photo_list"),
    path("upload/", views.PhotoCreateView.as_view(), name="photo_add"),
    path("<int:pk>/edit/", views.PhotoUpdateView.as_view(), name="photo_edit"),
    path("<int:pk>/delete/", views.PhotoDeleteView.as_view(), name="photo_delete"),
]
