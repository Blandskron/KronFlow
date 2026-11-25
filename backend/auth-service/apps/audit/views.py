from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets

from apps.shared.permissions import HasTenantPermission

from .models import AuditLog
from .serializers import AuditLogSerializer


@extend_schema_view(
    list=extend_schema(tags=["Audit"]),
    retrieve=extend_schema(tags=["Audit"]),
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    required_permission = "audit.read"
    permission_classes = [HasTenantPermission]

    def get_queryset(self):
        tenant_id = getattr(self.request, "authorized_tenant_id", None)
        if tenant_id is None:
            return AuditLog.objects.none()
        return AuditLog.objects.filter(tenant_id=tenant_id).order_by("-created_at")
