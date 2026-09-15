from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse

AUDIO_EXTENSIONS = ["mp3", "m4a", "aac", "wav", "ogg", "oga", "opus", "webm", "flac"]


class Photo(models.Model):
    image = models.ImageField(upload_to="gallery/%Y/")
    caption = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    date_taken = models.DateField(null=True, blank=True)
    people = models.ManyToManyField("genealogy.Person", blank=True, related_name="photos")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.caption or f"Photo #{self.pk}"


class Recording(models.Model):
    """An oral-history recording: a relative telling the family's stories in their own voice."""

    title = models.CharField(max_length=160)
    audio = models.FileField(upload_to="recordings/%Y/", validators=[FileExtensionValidator(AUDIO_EXTENSIONS)])
    language = models.CharField(max_length=60, blank=True, help_text="e.g. Gĩkũyũ, English, Kiswahili")
    recorded_on = models.DateField(null=True, blank=True)
    place = models.ForeignKey(
        "genealogy.Place", null=True, blank=True, on_delete=models.SET_NULL, related_name="recordings"
    )
    speakers = models.ManyToManyField("genealogy.Person", blank=True, related_name="recordings_given")
    people = models.ManyToManyField(
        "genealogy.Person", blank=True, related_name="recordings_about", verbose_name="people talked about"
    )
    description = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("gallery:recording_detail", args=[self.pk])

    @property
    def duration(self):
        if not self.duration_seconds:
            return ""
        minutes, seconds = divmod(self.duration_seconds, 60)
        return f"{minutes}:{seconds:02d}"
