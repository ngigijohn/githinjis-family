from django.contrib import admin
from django.utils.html import format_html

from .models import Photo


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ["thumbnail", "__str__", "date_taken", "uploaded_by", "created_at"]
    search_fields = ["caption", "description", "people__first_name", "people__last_name"]
    autocomplete_fields = ["people"]
    readonly_fields = ["uploaded_by", "created_at"]

    @admin.display(description="")
    def thumbnail(self, obj):
        if not obj.image:
            return ""
        return format_html('<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:6px">', obj.image.url)

    def save_model(self, request, obj, form, change):
        if not change and not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)
