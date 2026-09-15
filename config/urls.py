from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

admin.site.site_header = f"{settings.SITE_NAME} administration"
admin.site.site_title = settings.SITE_NAME
admin.site.index_title = "Family records"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("gallery/", include("gallery.urls")),
    path("", include("genealogy.urls")),
]

if settings.DEBUG or settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
