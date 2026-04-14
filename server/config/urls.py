from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", include("apps.health.urls")),
    path("api/projects/", include("apps.projects.urls")),
    path("api/media/", include("apps.media.urls")),
    path("api/render/", include("apps.render.urls")),
    path("api/import/", include("apps.import_vp.urls")),
]
