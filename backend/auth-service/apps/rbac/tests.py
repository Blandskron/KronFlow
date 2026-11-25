from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.rbac.models import MembershipRole, TenantRole
from apps.rbac.services import permissions_for_membership, role_permissions_for_membership, seed_roles_for_tenant
from apps.tenants.models import Tenant, TenantMembership


class RbacTests(TestCase):
    def test_seed_roles_for_tenant_creates_base_roles_and_permissions(self):
        user = get_user_model().objects.create_user(username="owner@example.com", email="owner@example.com")
        tenant = Tenant.objects.create(name="Acme", legal_name="Acme", created_by=user, plan=Tenant.Plan.STARTER, subscription_status=Tenant.SubscriptionStatus.ACTIVE)
        membership = TenantMembership.objects.create(user=user, tenant=tenant, status="active")

        seed_roles_for_tenant(tenant)
        role = TenantRole.objects.get(tenant=tenant, code="TENANT_ADMIN")
        MembershipRole.objects.create(membership=membership, role=role)

        self.assertIn("roles.assign", permissions_for_membership(membership))

    def test_open_source_workspace_grants_owner_permissions_without_a_subscription(self):
        user = get_user_model().objects.create_user(username="owner@example.com", email="owner@example.com")
        tenant = Tenant.objects.create(name="Free Co", legal_name="Free Co", created_by=user)
        membership = TenantMembership.objects.create(user=user, tenant=tenant, status="active")

        seed_roles_for_tenant(tenant)
        owner = TenantRole.objects.get(tenant=tenant, code="TENANT_OWNER")
        MembershipRole.objects.create(membership=membership, role=owner)

        self.assertIn("members.manage", role_permissions_for_membership(membership))
        self.assertIn("members.manage", permissions_for_membership(membership))
        self.assertIn("whatsapp.connect", permissions_for_membership(membership))
