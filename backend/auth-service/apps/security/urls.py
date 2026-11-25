from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import APIKeyViewSet, ServiceAccountViewSet, SigningKeyViewSet

router = DefaultRouter()
router.register("signing-keys", SigningKeyViewSet, basename="signing-key")
router.register("service-accounts", ServiceAccountViewSet, basename="service-account")
router.register("api-keys", APIKeyViewSet, basename="api-key")

urlpatterns = router.urls
