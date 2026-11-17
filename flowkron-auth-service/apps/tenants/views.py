import requests

from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, parsers, permissions, response, status, viewsets
from rest_framework.views import APIView
from rest_framework.exceptions import APIException, ValidationError

from apps.audit.models import AuditLog
from apps.audit.services import audit
from apps.accounts.tokens import issue_tokens
from apps.rbac.models import TenantRole
from apps.rbac.services import assert_delegable, permissions_for_membership, roles_for_membership
from apps.shared.permissions import HasTenantPermission
from apps.shared.responses import api_error, ok
from apps.shared.image_uploads import absolute_media_url, save_uploaded_image

from .models import Tenant, TenantInvitation, TenantMembership, TenantOperationalRuntime
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
from .services import activate_subscription, create_owned_tenant, ensure_open_workspace, provision_operational_runtime, rotate_operational_ingest_key, sync_operational_runtime_status, stop_workspace


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

    def perform_update(self, serializer):
        if "status" in self.request.data:
            raise ValidationError({"status": "Use the suspend or activate action."})
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        instance = Tenant.objects.select_for_update().get(pk=instance.pk)
        try:
            stop_workspace(instance)
        except requests.RequestException as exc:
            raise APIException("Could not stop the workspace; deletion was not completed.") from exc
        instance.delete()

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
            "whatsapp": "whatsapp.connect",
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
            tenant_id = getattr(self.request, "authorized_tenant_id", None)
            if tenant_id:
                queryset = queryset.filter(id=tenant_id)
            else:
                queryset = queryset.none()
        return queryset

    @decorators.action(detail=True, methods=["get", "post", "delete"], url_path="whatsapp")
    @transaction.atomic
    def whatsapp(self, request, pk=None):
        tenant = Tenant.objects.select_for_update().get(pk=self.get_object().pk)
        if tenant.status != Tenant.Status.ACTIVE:
            return api_error(status=409, error_code="WORKSPACE_INACTIVE", detail="El espacio de trabajo está inactivo.")
        if not settings.BAILEYS_INTERNAL_TOKEN:
            return api_error(status=503, error_code="WHATSAPP_DISABLED", detail="El conector de WhatsApp no está configurado.")
        endpoint = f"{settings.BAILEYS_SERVICE_URL.rstrip('/')}/internal/baileys/tenants/{tenant.pk}/session"
        try:
            if request.method == "POST":
                ensure_open_workspace(tenant)
            result = requests.request(
                request.method,
                endpoint,
                headers={"Authorization": f"Bearer {settings.BAILEYS_INTERNAL_TOKEN}"},
                timeout=12,
                allow_redirects=False,
            )
            result.raise_for_status()
            state = result.json()
            data = {"status": state["status"]}
            if isinstance(state.get("qr"), str) and state["qr"].startswith("data:image/png;base64,"):
                data["qr"] = state["qr"]
        except (requests.RequestException, ValueError, KeyError):
            return api_error(status=503, error_code="WHATSAPP_UNAVAILABLE", detail="No pudimos contactar el conector de WhatsApp. Reintenta en unos segundos.")
        result = ok(data)
        result["Cache-Control"] = "no-store"
        return result

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
        with transaction.atomic():
            owner = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            profile = owner.profile
            membership = owner.memberships.select_related("tenant").filter(
                status=TenantMembership.Status.ACTIVE, tenant__status=Tenant.Status.ACTIVE
            ).first()
            if membership:
                tenant = membership.tenant
                if profile.onboarding_completed_at or tenant.created_by_id != owner.pk:
                    return response.Response(
                        {"success": False, "code": "ONBOARDING_ALREADY_COMPLETED", "message": "El usuario ya tiene una empresa activa."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                serializer = TenantOnboardingSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                tenant, membership = create_owned_tenant(
                    owner,
                    serializer.validated_data["name"],
                    legal_name=serializer.validated_data.get("legal_name") or serializer.validated_data["name"],
                    tax_id=serializer.validated_data.get("tax_id", ""),
                    country=serializer.validated_data.get("country", "CL"),
                )
                audit(AuditLog.Event.TENANT_CREATED, request=request, tenant=tenant)
                audit(AuditLog.Event.TENANT_OWNER_ASSIGNED, request=request, tenant=tenant, membership_id=membership.id)

        try:
            ensure_open_workspace(tenant)
        except requests.RequestException:
            return response.Response(
                {"success": False, "code": "WORKSPACE_UNAVAILABLE", "message": "Tu empresa se guardó. Reintenta para habilitar su espacio de trabajo."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        profile.onboarding_completed_at = timezone.now()
        if not profile.account_activated_at:
            profile.account_activated_at = profile.email_verified_at
        profile.save(update_fields=["onboarding_completed_at", "account_activated_at", "updated_at"])
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
    @transaction.atomic
    def suspend(self, request, pk=None):
        tenant = Tenant.objects.select_for_update().get(pk=self.get_object().pk)
        try:
            stop_workspace(tenant)
        except requests.RequestException:
            return api_error(status=503, error_code="WORKSPACE_UNAVAILABLE", detail="No pudimos detener el espacio operativo y su conexión.")
        tenant.status = Tenant.Status.SUSPENDED
        tenant.save(update_fields=["status", "updated_at"])
        return ok(TenantSerializer(tenant).data)

    @decorators.action(detail=True, methods=["post"])
    @transaction.atomic
    def activate(self, request, pk=None):
        tenant = Tenant.objects.select_for_update().get(pk=self.get_object().pk)
        if TenantOperationalRuntime.objects.filter(tenant=tenant, status=TenantOperationalRuntime.Status.SUSPENDED).exists():
            try:
                sync_operational_runtime_status(tenant, "activate")
            except requests.RequestException:
                return api_error(status=503, error_code="WORKSPACE_UNAVAILABLE", detail="No pudimos reactivar el espacio operativo.")
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
    @transaction.atomic
    def update_member(self, request, pk=None, membership_id=None):
        tenant = self.get_object()
        Tenant.objects.select_for_update().get(pk=tenant.pk)
        membership = tenant.memberships.select_related("user").get(id=membership_id)
        for assigned in membership.membership_roles.select_related("role"):
            assert_delegable(request.authorized_membership, assigned.role)
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
        for code in serializer.validated_data.get("role_codes", []):
            assert_delegable(request.authorized_membership, TenantRole.objects.get(tenant=tenant, code=code))
        if serializer.validated_data.get("status", membership.status) != TenantMembership.Status.ACTIVE and _is_last_owner(membership):
            raise ValidationError("The workspace must retain an active owner.")
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
        membership_roles__role__tenant=tenant,
    ).distinct().count()


def _is_last_owner(membership):
    has_owner_role = membership.membership_roles.filter(role__code="TENANT_OWNER", role__tenant_id=membership.tenant_id).exists()
    return has_owner_role and _active_owner_count(membership.tenant) <= 1


def _would_remove_last_owner(membership, new_role_codes):
    if "TENANT_OWNER" in set(new_role_codes):
        return False
    return _is_last_owner(membership)
