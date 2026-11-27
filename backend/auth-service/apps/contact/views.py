from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.shared.responses import ok

from .models import ContactMessage
from .serializers import ContactMessageSerializer


@method_decorator(ensure_csrf_cookie, name="dispatch")
class ContactCsrfView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["Contact"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return ok({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class ContactMessageView(views.APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "contact"

    @extend_schema(tags=["Contact"], request=ContactMessageSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        )
        return ok({"id": message.id, "created_at": message.created_at}, status=status.HTTP_201_CREATED)


class ContactMessageDsarView(views.APIView):
    """Admin DSAR export & erasure for public landing contact messages by email (PRV-015)."""

    permission_classes = [permissions.IsAdminUser]

    @extend_schema(tags=["Contact"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        if not email:
            return Response(
                {"success": False, "code": "EMAIL_REQUIRED", "message": "Parametro email requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        items = list(
            ContactMessage.objects.filter(email__iexact=email)
            .order_by("-created_at")
            .values("id", "name", "email", "company", "phone", "message", "privacy_notice_version", "status", "created_at")
        )
        return ok({"email": email, "count": len(items), "items": items})

    @extend_schema(tags=["Contact"], responses=OpenApiTypes.OBJECT)
    def delete(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        if not email:
            return Response(
                {"success": False, "code": "EMAIL_REQUIRED", "message": "Parametro email requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = ContactMessage.objects.filter(email__iexact=email).delete()
        return ok({"email": email, "deleted": deleted})


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR")
