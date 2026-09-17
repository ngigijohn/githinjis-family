from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse

AUDIO_EXTENSIONS = ["mp3", "m4a", "aac", "wav", "ogg", "oga", "opus", "webm", "flac"]
DOCUMENT_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "webp", "tif", "tiff", "heic", "txt", "doc", "docx"]


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


class Document(models.Model):
    """A record that proves or tells part of the family's history: certificates, letters, land papers."""

    class Type(models.TextChoices):
        BIRTH = "birth", "Birth certificate"
        MARRIAGE = "marriage", "Marriage certificate"
        DEATH = "death", "Death certificate"
        SCHOOL = "school", "School record"
        LAND = "land", "Land or property document"
        IMMIGRATION = "immigration", "Immigration or travel record"
        LETTER = "letter", "Letter"
        NEWSPAPER = "newspaper", "Newspaper clipping"
        CHURCH = "church", "Church record"
        OTHER = "other", "Other document"

    class Privacy(models.TextChoices):
        FAMILY = "family", "Signed-in family only"
        PUBLIC = "public", "Anyone who visits"

    title = models.CharField(max_length=160)
    document_type = models.CharField("type", max_length=20, choices=Type.choices, default=Type.OTHER)
    file = models.FileField(upload_to="documents/%Y/", validators=[FileExtensionValidator(DOCUMENT_EXTENSIONS)])
    date = models.DateField(null=True, blank=True, help_text="The date on the document itself, if it has one.")
    date_approx = models.BooleanField("date is approximate", default=False)
    place = models.ForeignKey(
        "genealogy.Place", null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
    people = models.ManyToManyField("genealogy.Person", blank=True, related_name="documents")
    description = models.TextField(blank=True)
    source = models.CharField(
        max_length=200, blank=True, help_text="Where it came from: a registry, an archive, or the relative who kept it."
    )
    privacy = models.CharField(
        max_length=10,
        choices=Privacy.choices,
        default=Privacy.FAMILY,
        help_text="Certificates usually hold private details, so they stay with signed-in family by default.",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("gallery:document_detail", args=[self.pk])

    @property
    def is_image(self):
        return self.file.name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic"))

    @property
    def is_pdf(self):
        return self.file.name.lower().endswith(".pdf")

    @property
    def extension(self):
        return self.file.name.rsplit(".", 1)[-1].upper() if "." in self.file.name else "FILE"
