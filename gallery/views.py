from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from genealogy.models import Person

from .forms import DocumentForm, PhotoForm, RecordingForm
from .models import Document, Photo, Recording


def _person_from(request):
    person_id = request.GET.get("person", "")
    return Person.objects.filter(pk=person_id).first() if person_id.isdigit() else None


def visible_documents(user):
    """Documents anyone may see, plus the family-only ones once you're signed in."""
    documents = Document.objects.select_related("place__parent").prefetch_related("people")
    if user.is_authenticated:
        return documents
    return documents.filter(privacy=Document.Privacy.PUBLIC)


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
        context["tagged_people"] = Person.objects.filter(photos__isnull=False).distinct()
        context["selected_person"] = _person_from(self.request)
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


class RecordingListView(ListView):
    model = Recording
    paginate_by = 20
    template_name = "gallery/recording_list.html"
    context_object_name = "recordings"

    def get_queryset(self):
        qs = Recording.objects.select_related("place__parent").prefetch_related("speakers")
        person = _person_from(self.request)
        if person:
            qs = qs.filter(speakers=person) | qs.filter(people=person)
        if self.request.GET.get("language"):
            qs = qs.filter(language__iexact=self.request.GET["language"])
        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "selected_person": _person_from(self.request),
                "languages": Recording.objects.exclude(language="").values_list("language", flat=True).distinct().order_by("language"),
                "speakers": Person.objects.filter(recordings_given__isnull=False).distinct(),
                "filters": self.request.GET,
            }
        )
        return context


class RecordingDetailView(DetailView):
    model = Recording
    template_name = "gallery/recording_detail.html"
    context_object_name = "recording"

    def get_queryset(self):
        return Recording.objects.select_related("place__parent", "uploaded_by").prefetch_related("speakers", "people")


class RecordingFormMixin:
    model = Recording
    form_class = RecordingForm
    template_name = "gallery/recording_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["languages"] = sorted({"Gĩkũyũ", "English", "Kiswahili"} | set(Recording.objects.exclude(language="").values_list("language", flat=True)))
        return context


class RecordingCreateView(PermissionRequiredMixin, RecordingFormMixin, CreateView):
    permission_required = "gallery.add_recording"

    def get_initial(self):
        initial = super().get_initial()
        person = _person_from(self.request)
        if person:
            initial["speakers"] = [person.pk]
        return initial

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        messages.success(self.request, "Recording added.")
        return super().form_valid(form)


class RecordingUpdateView(PermissionRequiredMixin, RecordingFormMixin, UpdateView):
    permission_required = "gallery.change_recording"

    def form_valid(self, form):
        messages.success(self.request, "Recording updated.")
        return super().form_valid(form)


class RecordingDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = "gallery.delete_recording"
    model = Recording
    template_name = "gallery/recording_confirm_delete.html"
    success_url = reverse_lazy("gallery:recording_list")

    def form_valid(self, form):
        messages.success(self.request, "Recording deleted.")
        return super().form_valid(form)


class DocumentListView(ListView):
    model = Document
    paginate_by = 24
    template_name = "gallery/document_list.html"
    context_object_name = "documents"

    def get_queryset(self):
        qs = visible_documents(self.request.user)
        person = _person_from(self.request)
        if person:
            qs = qs.filter(people=person)
        if self.request.GET.get("type"):
            qs = qs.filter(document_type=self.request.GET["type"])
        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shown = visible_documents(self.request.user)
        context.update(
            {
                "selected_person": _person_from(self.request),
                "types": [(value, label) for value, label in Document.Type.choices if shown.filter(document_type=value).exists()],
                "people": Person.objects.filter(documents__in=shown).distinct(),
                "filters": self.request.GET,
                "hidden_count": Document.objects.count() - shown.count(),
            }
        )
        return context


class DocumentDetailView(DetailView):
    model = Document
    template_name = "gallery/document_detail.html"
    context_object_name = "document"

    def get_queryset(self):
        return visible_documents(self.request.user)


class DocumentCreateView(PermissionRequiredMixin, CreateView):
    permission_required = "gallery.add_document"
    model = Document
    form_class = DocumentForm
    template_name = "gallery/document_form.html"

    def get_initial(self):
        initial = super().get_initial()
        person = _person_from(self.request)
        if person:
            initial["people"] = [person.pk]
        return initial

    def form_valid(self, form):
        form.instance.uploaded_by = self.request.user
        messages.success(self.request, "Document added to the archive.")
        return super().form_valid(form)


class DocumentUpdateView(PermissionRequiredMixin, UpdateView):
    permission_required = "gallery.change_document"
    model = Document
    form_class = DocumentForm
    template_name = "gallery/document_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Document updated.")
        return super().form_valid(form)


class DocumentDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = "gallery.delete_document"
    model = Document
    template_name = "gallery/document_confirm_delete.html"
    success_url = reverse_lazy("gallery:document_list")

    def form_valid(self, form):
        messages.success(self.request, "Document deleted.")
        return super().form_valid(form)
