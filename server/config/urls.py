from django.conf import settings
from django.conf.urls.static import static
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

# Serve thumbnails (and any other MEDIA_ROOT files) directly from the sidecar.
# Also expose proxies under /proxies/ and rendered exports under /renders/.
# Safe because the sidecar binds to 127.0.0.1 only.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static("/proxies/", document_root=settings.KINORO_PROXY_DIR)
urlpatterns += static("/renders/", document_root=settings.KINORO_RENDER_DIR)
