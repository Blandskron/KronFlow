from rest_framework.routers import DefaultRouter

from .views import UserSessionViewSet

router = DefaultRouter()
router.register("", UserSessionViewSet, basename="session")

urlpatterns = router.urls
