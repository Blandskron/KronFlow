from .models import Tenant


FREE_ENTITLEMENTS = {
    "tenants.read",
}

PAID_ENTITLEMENTS = {
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

PLAN_ENTITLEMENTS = {
    Tenant.Plan.FREE: FREE_ENTITLEMENTS,
    Tenant.Plan.STARTER: PAID_ENTITLEMENTS,
    Tenant.Plan.PRO: PAID_ENTITLEMENTS,
    Tenant.Plan.ENTERPRISE: PAID_ENTITLEMENTS,
}


def tenant_subscription_is_enabled(tenant):
    if tenant.plan == Tenant.Plan.FREE:
        return tenant.subscription_status == Tenant.SubscriptionStatus.FREE
    return tenant.subscription_status in {
        Tenant.SubscriptionStatus.ACTIVE,
        Tenant.SubscriptionStatus.TRIALING,
    }


def entitlements_for_tenant(tenant):
    if not tenant or not tenant_subscription_is_enabled(tenant):
        return []
    return sorted(PLAN_ENTITLEMENTS.get(tenant.plan, FREE_ENTITLEMENTS))


def subscription_summary(tenant):
    if not tenant:
        return None
    return {
        "plan": tenant.plan,
        "status": tenant.subscription_status,
        "entitlements": entitlements_for_tenant(tenant),
        "current_period_end": tenant.subscription_current_period_end.isoformat() if tenant.subscription_current_period_end else None,
        "requires_paid_plan": tenant.plan == Tenant.Plan.FREE,
    }
