from django.conf import settings
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, parsers, permissions, response, status, viewsets
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.accounts.tokens import issue_tokens
from apps.rbac.services import permissions_for_membership, roles_for_membership
from apps.shared.permissions import HasTenantPermission
from apps.shared.responses import ok
from apps.shared.image_uploads import absolute_media_url, save_uploaded_image

from .models import Tenant, TenantInvitation, TenantMembership
from .serializers import (
    AcceptInvitationSerializer,
    InvitationTokenSerializer,
    InviteSerializer,
    MemberUpdateSerializer,
    TenantInvitationSerializer,
    TenantMembershipSerializer,
    TenantOnboardingSerializer,
    TenantSerializer,
    get_pending_invitation,
)
from .services import activate_subscription, create_owned_tenant, provision_operational_runtime, rotate_operational_ingest_key


@extend_schema_view(
    list=extend_schema(tags=["Tenants"]),
    retrieve=extend_schema(tags=["Tenants"]),
    create=extend_schema(tags=["Tenants"]),
    update=extend_schema(tags=["Tenants"]),
    partial_update=extend_schema(tags=["Tenants"]),
    destroy=extend_schema(tags=["Tenants"]),
    suspend=extend_schema(tags=["Tenants"]),
    activate=extend_schema(tags=["Tenants"]),
    members=extend_schema(tags=["Tenant Members"]),
    update_member=extend_schema(tags=["Tenant Members"]),
            invite=extend_schema(tags=["Tenant Invitations"]),
            invitations=extend_schema(tags=["Tenant Invitations"]),
            revoke_invitation=extend_schema(tags=["Tenant Invitations"]),
            provision_runtime=extend_schema(tags=["Tenant Operational Runtime"]),
    activate_subscription=extend_schema(tags=["Tenant Billing"]),
    runtime=extend_schema(tags=["Tenant Operational Runtime"]),
    rotate_ingest_key=extend_schema(tags=["Tenant Operational Runtime"]),
)
class TenantViewSet(viewsets.ModelViewSet):
    serializer_class = TenantSerializer

    def get_permissions(self):
        permission_by_action = {
            "list": None,
            "create": None,
            "retrieve": "tenants.read",
            "update": "tenants.manage",
            "partial_update": "tenants.manage",
            "destroy": "tenants.manage",
            "suspend": "tenants.manage",
            "activate": "tenants.manage",
            "members": "members.manage",
            "update_member": "members.manage",
            "invite": "members.manage",
            "invitations": "members.manage",
            "revoke_invitation": "members.manage",
            "logo": "tenants.manage",
            "provision_runtime": "tenants.manage",
            "activate_subscription": "tenants.manage",
            "runtime": "tenants.read",
            "rotate_ingest_key": "tenants.manage",
            "onboarding": None,
        }
        self.required_permission = permission_by_action.get(self.action)
        if self.required_permission:
            return [HasTenantPermission()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Tenant.objects.none()
        queryset = Tenant.objects.filter(memberships__user=self.request.user).distinct()
        if getattr(self, "required_permission", None):
            tenant_id = (
                self.request.headers.get("X-Tenant-ID")
                or self.request.query_params.get("tenant_id")
                or (self.request.auth.get("tenant_id") if self.request.auth else None)
            )
            if tenant_id:
                queryset = queryset.filter(id=tenant_id)
            else:
                queryset = queryset.none()
        return queryset

    def perform_create(self, serializer):
        tenant, _ = create_owned_tenant(
            self.request.user,
            serializer.validated_data["name"],
            legal_name=serializer.validated_data.get("legal_name") or serializer.validated_data["name"],
            tax_id=serializer.validated_data.get("tax_id", ""),
            country=serializer.validated_data.get("country", "CL"),
        )
        serializer.instance = tenant
        audit(AuditLog.Event.TENANT_CREATED, request=self.request, tenant=tenant)
        audit(AuditLog.Event.TENANT_OWNER_ASSIGNED, request=self.request, tenant=tenant)

    @decorators.action(detail=False, methods=["post"], url_path="onboarding")
    def onboarding(self, request):
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.email_verified_at:
            return response.Response(
                {"success": False, "code": "AUTH_EMAIL_NOT_VERIFIED", "message": "Debes verificar tu correo antes de crear empresa.", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        existing_membership = request.user.memberships.filter(status=TenantMembership.Status.ACTIVE, tenant__status=Tenant.Status.ACTIVE).first()
        if existing_membership:
            return response.Response(
                {"success": False, "code": "ONBOARDING_ALREADY_COMPLETED", "message": "El usuario ya tiene una empresa activa.", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = TenantOnboardingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant, membership = create_owned_tenant(
            request.user,
            serializer.validated_data["name"],
            legal_name=serializer.validated_data.get("legal_name") or serializer.validated_data["name"],
            tax_id=serializer.validated_data.get("tax_id", ""),
            country=serializer.validated_data.get("country", "CL"),
        )
        profile.onboarding_completed_at = timezone.now()
        if not profile.account_activated_at:
            profile.account_activated_at = profile.email_verified_at
        profile.save(update_fields=["onboarding_completed_at", "account_activated_at", "updated_at"])
        audit(AuditLog.Event.TENANT_CREATED, request=request, tenant=tenant)
        audit(AuditLog.Event.TENANT_OWNER_ASSIGNED, request=request, tenant=tenant, membership_id=membership.id)
        refresh, session = issue_tokens(request.user, membership, request, amr=request.auth.get("amr", "pwd") if request.auth else "pwd")
        return ok(
            {
                "tenant": TenantSerializer(tenant).data,
                "membership": TenantMembershipSerializer(membership).data,
                "onboarding_completed_at": profile.onboarding_completed_at,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "session_id": session.id,
                "tenant_id": membership.tenant_id,
                "roles": roles_for_membership(membership),
                "permissions": permissions_for_membership(membership),
            },
            status=status.HTTP_201_CREATED,
        )

    @decorators.action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        tenant = self.get_object()
        tenant.status = Tenant.Status.SUSPENDED
        tenant.save(update_fields=["status", "updated_at"])
        return ok(TenantSerializer(tenant).data)

    @decorators.action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        tenant = self.get_object()
        tenant.status = Tenant.Status.ACTIVE
        tenant.save(update_fields=["status", "updated_at"])
        return ok(TenantSerializer(tenant).data)

    @decorators.action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        tenant = self.get_object()
        if request.method == "GET":
            memberships = tenant.memberships.select_related("user", "user__profile").prefetch_related("membership_roles__role")
            return ok(TenantMembershipSerializer(memberships, many=True).data)
        user = request.user
        membership, _ = TenantMembership.objects.get_or_create(user=user, tenant=tenant, defaults={"status": TenantMembership.Status.ACTIVE, "joined_at": timezone.now()})
        audit(AuditLog.Event.MEMBER_CHANGED, request=request, tenant=tenant, action="member_added")
        return response.Response({"success": True, "data": TenantMembershipSerializer(membership).data}, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=["patch", "delete"], url_path=r"members/(?P<membership_id>[^/.]+)")
    def update_member(self, request, pk=None, membership_id=None):
        tenant = self.get_object()
        membership = tenant.memberships.select_related("user").get(id=membership_id)
        if membership.user_id == request.user.id and request.method == "DELETE":
            return response.Response(
                {"success": False, "code": "MEMBER_SELF_REMOVE_DENIED", "message": "No puedes remover tu propia membresia.", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if request.method == "DELETE":
            if _is_last_owner(membership):
                return response.Response(
                    {"success": False, "code": "LAST_OWNER_REMOVAL_DENIED", "message": "No puedes remover al unico owner del tenant.", "details": {}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            membership.status = TenantMembership.Status.REVOKED
            membership.revoked_at = timezone.now()
            membership.save(update_fields=["status", "revoked_at", "updated_at"])
            audit(AuditLog.Event.MEMBER_REMOVED, request=request, tenant=tenant, membership_id=membership.id)
            return ok(TenantMembershipSerializer(membership).data)
        serializer = MemberUpdateSerializer(data=request.data, context={"membership": membership})
        serializer.is_valid(raise_exception=True)
        if "role_codes" in serializer.validated_data and _would_remove_last_owner(membership, serializer.validated_data["role_codes"]):
            return response.Response(
                {"success": False, "code": "LAST_OWNER_ROLE_CHANGE_DENIED", "message": "El tenant debe conservar al menos un owner activo.", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership = serializer.save()
        audit(AuditLog.Event.MEMBER_ROLE_CHANGED, request=request, tenant=tenant, membership_id=membership.id)
        return ok(TenantMembershipSerializer(membership).data)

    @decorators.action(detail=True, methods=["post"])
    def invite(self, request, pk=None):
        tenant = self.get_object()
        serializer = InviteSerializer(data=request.data, context={"request": request, "tenant": tenant})
        serializer.is_valid(raise_exception=True)
        invitation = serializer.save()
        audit(AuditLog.Event.INVITATION_SENT, request=request, tenant=tenant, email=invitation.email, role_code=invitation.role_code)
        payload = {
            "invitation": TenantInvitationSerializer(invitation).data,
            "email_sent": invitation.email_sent,
        }
        if settings.DEBUG:
            payload["token"] = invitation.plain_token
            payload["invite_url"] = invitation.invite_url
        return ok(payload, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=["get"], url_path="invitations")
    def invitations(self, request, pk=None):
        tenant = self.get_object()
        invitations = tenant.invitations.select_related("invited_by", "tenant").order_by("-created_at")
        return ok(TenantInvitationSerializer(invitations, many=True).data)

    @decorators.action(detail=True, methods=["post"], url_path=r"invitations/(?P<invitation_id>[^/.]+)/revoke")
    def revoke_invitation(self, request, pk=None, invitation_id=None):
        tenant = self.get_object()
        invitation = tenant.invitations.filter(id=invitation_id, status=TenantInvitation.Status.PENDING).first()
        if not invitation:
            return response.Response(
                {"success": False, "code": "INVITATION_NOT_FOUND", "message": "Invitacion pendiente no encontrada.", "details": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
        invitation.status = TenantInvitation.Status.REVOKED
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["status", "revoked_at"])
        audit(AuditLog.Event.INVITATION_REVOKED, request=request, tenant=tenant, invitation_id=invitation.id)
        return ok(TenantInvitationSerializer(invitation).data)

    @decorators.action(detail=True, methods=["post"], url_path="logo", parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def logo(self, request, pk=None):
        tenant = self.get_object()
        image = request.FILES.get("image")
        if not image:
            return response.Response(
                {"success": False, "code": "IMAGE_REQUIRED", "message": "Debes enviar una imagen.", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        stored_path = save_uploaded_image(image, folder=f"tenants/{tenant.id}/logo", max_size=(800, 800))
        tenant.logo_url = absolute_media_url(request, stored_path)
        tenant.save(update_fields=["logo_url", "updated_at"])
        audit(AuditLog.Event.MEMBER_CHANGED, request=request, tenant=tenant, action="tenant_logo_uploaded")
        return ok(TenantSerializer(tenant).data)

    @decorators.action(detail=True, methods=["get"], url_path="runtime")
    def runtime(self, request, pk=None):
        tenant = self.get_object()
        return ok(TenantSerializer(tenant).data.get("operational_runtime"))

    @decorators.action(detail=True, methods=["post"], url_path="runtime/provision")
    def provision_runtime(self, request, pk=None):
        tenant = self.get_object()
        try:
            runtime, ingest_key = provision_operational_runtime(tenant)
        except Exception as exc:
            return response.Response(
                {"success": False, "code": "OPERATIONAL_PROVISION_FAILED", "message": str(exc), "details": {}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        audit(AuditLog.Event.MEMBER_CHANGED, request=request, tenant=tenant, action="operational_runtime_provisioned")
        return ok(
            {
                "runtime": TenantSerializer(tenant).data.get("operational_runtime"),
                "ingest_key": ingest_key,
                "show_ingest_key_once": bool(ingest_key),
            },
            status=status.HTTP_201_CREATED,
        )

    @decorators.action(detail=True, methods=["post"], url_path="subscription/activate")
    def activate_subscription(self, request, pk=None):
        tenant = self.get_object()
        plan = request.data.get("plan") or Tenant.Plan.STARTER
        provider = request.data.get("provider", "")
        external_id = request.data.get("external_id", "")
        try:
            activate_subscription(tenant, plan=plan, provider=provider, external_id=external_id)
        except Exception as exc:
            return response.Response(
                {"success": False, "code": "SUBSCRIPTION_ACTIVATION_FAILED", "message": str(exc), "details": {}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        audit(AuditLog.Event.MEMBER_CHANGED, request=request, tenant=tenant, action="subscription_activated", plan=plan)
        return ok(TenantSerializer(tenant).data)

    @decorators.action(detail=True, methods=["post"], url_path="runtime/rotate-ingest-key")
    def rotate_ingest_key(self, request, pk=None):
        tenant = self.get_object()
        try:
            data = rotate_operational_ingest_key(tenant)
        except Exception as exc:
            return response.Response(
                {"success": False, "code": "INGEST_KEY_ROTATION_FAILED", "message": str(exc), "details": {}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        audit(AuditLog.Event.MEMBER_CHANGED, request=request, tenant=tenant, action="ingest_key_rotated")
        return ok({**data, "show_ingest_key_once": True})


class AcceptInvitationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Tenant Invitations"], request=AcceptInvitationSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        if getattr(serializer, "created_user", None):
            audit(AuditLog.Event.USER_CREATED, request=request, user=membership.user, source="tenant_invitation")
            audit(AuditLog.Event.ACCOUNT_ACTIVATED, request=request, user=membership.user, source="tenant_invitation")
        audit(AuditLog.Event.INVITATION_ACCEPTED, request=request, user=membership.user, tenant=membership.tenant, membership_id=membership.id)
        return ok(TenantMembershipSerializer(membership).data)


class InvitationPreviewView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Tenant Invitations"], request=None, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        serializer = InvitationTokenSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        invitation = get_pending_invitation(serializer.validated_data["token"])
        return ok(TenantInvitationSerializer(invitation).data)


class RejectInvitationView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["Tenant Invitations"], request=InvitationTokenSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = InvitationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = get_pending_invitation(serializer.validated_data["token"])
        invitation.status = TenantInvitation.Status.REJECTED
        invitation.rejected_at = timezone.now()
        invitation.save(update_fields=["status", "rejected_at"])
        return ok(TenantInvitationSerializer(invitation).data)


def _active_owner_count(tenant):
    return TenantMembership.objects.filter(
        tenant=tenant,
        status=TenantMembership.Status.ACTIVE,
        membership_roles__role__code="TENANT_OWNER",
    ).distinct().count()


def _is_last_owner(membership):
    has_owner_role = membership.membership_roles.filter(role__code="TENANT_OWNER").exists()
    return has_owner_role and _active_owner_count(membership.tenant) <= 1


def _would_remove_last_owner(membership, new_role_codes):
    if "TENANT_OWNER" in set(new_role_codes):
        return False
    return _is_last_owner(membership)
