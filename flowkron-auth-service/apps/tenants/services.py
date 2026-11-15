from django.db import transaction
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils import timezone
import requests

from apps.rbac.models import MembershipRole, TenantRole
from apps.rbac.services import seed_roles_for_tenant

from .models import Tenant, TenantMembership, TenantOperationalRuntime


@transaction.atomic
def create_owned_tenant(user, name, **extra_fields):
    tenant = Tenant.objects.create(name=name, legal_name=extra_fields.pop("legal_name", name), created_by=user, **extra_fields)
    membership = TenantMembership.objects.create(user=user, tenant=tenant, status=TenantMembership.Status.ACTIVE, joined_at=timezone.now())
    seed_roles_for_tenant(tenant)
    owner = TenantRole.objects.get(tenant=tenant, code="TENANT_OWNER")
    MembershipRole.objects.create(membership=membership, role=owner)
    return tenant, membership


def activate_subscription(tenant, plan, provider="", external_id="", current_period_end=None):
    tenant.plan = plan
    tenant.subscription_status = Tenant.SubscriptionStatus.ACTIVE
    tenant.subscription_provider = provider
    tenant.subscription_external_id = external_id
    tenant.subscription_current_period_end = current_period_end
    tenant.save(
        update_fields=[
            "plan",
            "subscription_status",
            "subscription_provider",
            "subscription_external_id",
            "subscription_current_period_end",
            "updated_at",
        ]
    )
    provision_operational_runtime(tenant)
    return tenant


def provision_operational_runtime(tenant):
    runtime, _ = TenantOperationalRuntime.objects.get_or_create(
        tenant=tenant,
        defaults={"status": TenantOperationalRuntime.Status.PENDING, "plan": tenant.plan},
    )
    url = f"{settings.OPERATIONAL_SERVICE_URL.rstrip('/')}/internal/tenants/provision"
    payload = {
        "auth_tenant_id": tenant.id,
        "tenant_slug": tenant.slug,
        "tenant_name": tenant.name,
        "plan": tenant.plan,
    }
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"X-Internal-Token": settings.OPERATIONAL_INTERNAL_TOKEN},
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        payload = _unwrap_operational_response(body)
        data = payload.get("runtime", payload)
        runtime.schema_name = data.get("schema_name", runtime.schema_name)
        runtime.tenant_code = data.get("tenant_code", runtime.tenant_code)
        runtime.plan = data.get("plan", tenant.plan)
        runtime.status = data.get("status", TenantOperationalRuntime.Status.ACTIVE)
        runtime.provisioned_at = _parse_operational_datetime(data.get("provisioned_at")) or runtime.provisioned_at
        runtime.suspended_at = _parse_operational_datetime(data.get("suspended_at"))
        runtime.last_sync_at = timezone.now()
        runtime.last_error = ""
        runtime.save()
        return runtime, payload.get("ingest_key")
    except requests.RequestException as exc:
        runtime.status = TenantOperationalRuntime.Status.PROVISION_FAILED
        runtime.plan = tenant.plan
        runtime.last_sync_at = timezone.now()
        runtime.last_error = str(exc)
        runtime.save(update_fields=["status", "plan", "last_sync_at", "last_error", "updated_at"])
        raise


def sync_operational_runtime_status(tenant, action):
    runtime = getattr(tenant, "operational_runtime", None)
    url = f"{settings.OPERATIONAL_SERVICE_URL.rstrip('/')}/internal/tenants/{tenant.id}/{action}"
    response = requests.post(
        url,
        headers={"X-Internal-Token": settings.OPERATIONAL_INTERNAL_TOKEN},
        timeout=15,
    )
    response.raise_for_status()
    data = _unwrap_operational_response(response.json())
    if runtime:
        runtime.status = data.get("status", runtime.status)
        runtime.suspended_at = _parse_operational_datetime(data.get("suspended_at"))
        runtime.last_sync_at = timezone.now()
        runtime.last_error = ""
        runtime.save()
    return data


def rotate_operational_ingest_key(tenant):
    url = f"{settings.OPERATIONAL_SERVICE_URL.rstrip('/')}/internal/tenants/{tenant.id}/rotate-ingest-key"
    response = requests.post(
        url,
        headers={"X-Internal-Token": settings.OPERATIONAL_INTERNAL_TOKEN},
        timeout=15,
    )
    response.raise_for_status()
    return _unwrap_operational_response(response.json())


def _parse_operational_datetime(value):
    if not value:
        return None
    if hasattr(value, "tzinfo"):
        return value
    parsed = parse_datetime(str(value))
    return parsed


def _unwrap_operational_response(body):
    if isinstance(body, dict) and body.get("success") is True and isinstance(body.get("data"), dict):
        return body["data"]
    return body
