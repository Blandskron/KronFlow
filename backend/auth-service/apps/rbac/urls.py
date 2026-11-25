from rest_framework.routers import DefaultRouter

from .views import MembershipRoleViewSet, PermissionViewSet, TenantRoleViewSet

router = DefaultRouter()
router.register("permissions", PermissionViewSet, basename="permission")
router.register("roles", TenantRoleViewSet, basename="role")
router.register("membership-roles", MembershipRoleViewSet, basename="membership-role")

urlpatterns = router.urls
