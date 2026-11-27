from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, viewsets

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.shared.responses import ok

from .models import UserSession
from .revocation import revoke_session
from .serializers import UserSessionSerializer


@extend_schema_view(
    list=extend_schema(tags=["Sessions"]),
    retrieve=extend_schema(tags=["Sessions"]),
    revoke=extend_schema(tags=["Sessions"]),
    status=extend_schema(tags=["Sessions"]),
)
class UserSessionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserSessionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return UserSession.objects.none()
        return UserSession.objects.filter(user=self.request.user).order_by("-created_at")

    @decorators.action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        session = self.get_object()
        session.status = UserSession.Status.REVOKED
        session.revoked_at = timezone.now()
        session.save(update_fields=["status", "revoked_at", "updated_at"])
        revoke_session(session.id)
        audit(AuditLog.Event.SESSION_REVOKED, request=request, session_id=session.id)
        return ok({"revoked": True})

    @decorators.action(detail=False, methods=["get"], url_path="status")
    def status(self, request):
        session_id = request.auth.get("session_id") if request.auth else None
        session = UserSession.objects.filter(id=session_id, user=request.user).first()
        return ok({"active": bool(session and session.is_active), "session": UserSessionSerializer(session).data if session else None})
