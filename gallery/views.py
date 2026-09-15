from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from genealogy.models import Person

from .forms import PhotoForm
from .models import Photo


class PhotoListView(ListView):
    model = Photo
    paginate_by = 24
    template_name = "gallery/photo_list.html"
    context_object_name = "photos"

    def get_queryset(self):
        qs = Photo.objects.prefetch_related("people")
        person_id = self.request.GET.get("person")
        if person_id and person_id.isdigit():
            qs = qs.filter(people__pk=person_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person_id = self.request.GET.get("person")
        context["tagged_people"] = Person.objects.filter(photos__isnull=False).distinct()
        context["selected_person"] = (
            Person.objects.filter(pk=person_id).first() if person_id and person_id.isdigit() else None
        )
        context["lightbox"] = [
            {
                "src": photo.image.url,
                "caption": str(photo),
                "date": photo.date_taken.strftime("%d %b %Y") if photo.date_taken else "",
                "people": [p.full_name for p in photo.people.all()],
            }
            for photo in context["photos"]
        ]
        return context


class PhotoCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "gallery.add_photo"
    model = Photo
    form_class = PhotoForm
    template_name = "gallery/photo_form.html"
    success_url = reverse_lazy("gallery:photo_list")

    def get_initial(self):
        initial = super().get_initial()
        person_id = self.request.GET.get("person")
        if person_id and person_id.isdigit():
            initial["people"] = [person_id]
        return initial

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        messages.success(self.request, "Photo added to the gallery.")
        return super().form_valid(form)


class PhotoUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "gallery.change_photo"
    model = Photo
    form_class = PhotoForm
    template_name = "gallery/photo_form.html"
    success_url = reverse_lazy("gallery:photo_list")

    def form_valid(self, form):
        messages.success(self.request, "Photo updated.")
        return super().form_valid(form)


class PhotoDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = "gallery.delete_photo"
    model = Photo
    template_name = "gallery/photo_confirm_delete.html"
    success_url = reverse_lazy("gallery:photo_list")

    def form_valid(self, form):
        messages.success(self.request, "Photo deleted.")
        return super().form_valid(form)
