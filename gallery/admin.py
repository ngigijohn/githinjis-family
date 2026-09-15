from django.contrib import admin
from django.utils.html import format_html

from .models import Photo, Recording


class UploaderAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        if not change and not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Photo)
class PhotoAdmin(UploaderAdmin):
    list_display = ["thumbnail", "__str__", "date_taken", "uploaded_by", "created_at"]
    search_fields = ["caption", "description", "people__first_name", "people__last_name"]
    autocomplete_fields = ["people"]
    readonly_fields = ["uploaded_by", "created_at"]

    @admin.display(description="")
    def thumbnail(self, obj):
        if not obj.image:
            return ""
        return format_html('<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:6px">', obj.image.url)


@admin.register(Recording)
class RecordingAdmin(UploaderAdmin):
    list_display = ["title", "language", "recorded_on", "place", "duration", "uploaded_by"]
    list_filter = ["language"]
    search_fields = ["title", "description", "transcript", "speakers__first_name", "people__first_name"]
    autocomplete_fields = ["place", "speakers", "people"]
    readonly_fields = ["uploaded_by", "created_at"]
