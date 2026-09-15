from django.urls import path

from . import views

app_name = "gallery"

urlpatterns = [
    path("", views.PhotoListView.as_view(), name="photo_list"),
    path("upload/", views.PhotoCreateView.as_view(), name="photo_add"),
    path("<int:pk>/edit/", views.PhotoUpdateView.as_view(), name="photo_edit"),
    path("<int:pk>/delete/", views.PhotoDeleteView.as_view(), name="photo_delete"),
    path("recordings/", views.RecordingListView.as_view(), name="recording_list"),
    path("recordings/add/", views.RecordingCreateView.as_view(), name="recording_add"),
    path("recordings/<int:pk>/", views.RecordingDetailView.as_view(), name="recording_detail"),
    path("recordings/<int:pk>/edit/", views.RecordingUpdateView.as_view(), name="recording_edit"),
    path("recordings/<int:pk>/delete/", views.RecordingDeleteView.as_view(), name="recording_delete"),
]
