from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AcceptInvitationView,
    InvitationPreviewView,
    PublicTenantPrivacyProfileView,
    RejectInvitationView,
    TenantViewSet,
)

router = DefaultRouter()
router.register("", TenantViewSet, basename="tenant")

urlpatterns = [
    path("invitations/preview/", InvitationPreviewView.as_view(), name="invitation-preview"),
    path("invitations/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    path("invitations/reject/", RejectInvitationView.as_view(), name="invitation-reject"),
    path("privacy-profile/<slug:slug>/", PublicTenantPrivacyProfileView.as_view(), name="tenant-privacy-profile"),
] + router.urls
