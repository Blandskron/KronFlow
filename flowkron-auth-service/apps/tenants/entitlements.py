from .models import Tenant


WORKSPACE_ENTITLEMENTS = {
    "users.read",
    "users.create",
    "roles.assign",
    "agents.create",
    "whatsapp.connect",
    "crm.manage",
    "audit.read",
    "auth.verify_token",
    "sessions.validate",
    "tenants.read",
    "tenants.manage",
    "members.manage",
    "api_keys.manage",
    "signing_keys.rotate",
    "service_accounts.manage",
}

def entitlements_for_tenant(tenant):
    if not tenant or tenant.status == Tenant.Status.ARCHIVED:
        return []
    if tenant.status == Tenant.Status.SUSPENDED:
        return ["tenants.manage", "tenants.read"]
    return sorted(WORKSPACE_ENTITLEMENTS)


def subscription_summary(tenant):
    if not tenant:
        return None
    return {
        "plan": tenant.plan,
        "status": tenant.subscription_status,
        "entitlements": entitlements_for_tenant(tenant),
        "current_period_end": tenant.subscription_current_period_end.isoformat() if tenant.subscription_current_period_end else None,
        "requires_paid_plan": False,
    }
