from rest_framework.routers import DefaultRouter

from .views import MediaAssetViewSet

router = DefaultRouter()
router.register(r"", MediaAssetViewSet, basename="media")

urlpatterns = router.urls
