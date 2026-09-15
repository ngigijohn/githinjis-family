from django.conf import settings
from django.db import models


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
