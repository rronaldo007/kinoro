from rest_framework.routers import DefaultRouter

from .views import RenderJobViewSet

router = DefaultRouter()
router.register(r"", RenderJobViewSet, basename="render")

urlpatterns = router.urls
