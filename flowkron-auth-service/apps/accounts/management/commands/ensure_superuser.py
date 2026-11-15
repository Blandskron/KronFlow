from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.rbac.models import MembershipRole, TenantRole
from apps.rbac.services import seed_roles_for_tenant
from apps.tenants.models import Tenant, TenantMembership


class Command(BaseCommand):
    help = "Crea o actualiza un superuser desde variables de entorno."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--username", required=False)

    def handle(self, *args, **options):
        email = options["email"].lower()
        username = (options.get("username") or email).lower()
        password = options["password"]
        User = get_user_model()

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True, "is_active": True},
        )
        changed = created
        if user.email != email:
            user.email = email
            changed = True
        if not user.is_staff or not user.is_superuser or not user.is_active:
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            changed = True
        user.set_password(password)
        user.save()

        if hasattr(user, "profile") and not user.profile.email_verified_at:
            user.profile.email_verified_at = timezone.now()
            user.profile.save(update_fields=["email_verified_at", "updated_at"])

        tenant, _ = Tenant.objects.get_or_create(
            slug=settings.IAM_PLATFORM_TENANT_SLUG,
            defaults={
                "name": "BLANDSKRON",
                "legal_name": "BLANDSKRON",
                "country": "CL",
                "created_by": user,
            },
        )
        seed_roles_for_tenant(tenant)
        membership, _ = TenantMembership.objects.get_or_create(
            user=user,
            tenant=tenant,
            defaults={"status": TenantMembership.Status.ACTIVE, "joined_at": timezone.now()},
        )
        if membership.status != TenantMembership.Status.ACTIVE:
            membership.status = TenantMembership.Status.ACTIVE
            membership.joined_at = membership.joined_at or timezone.now()
            membership.revoked_at = None
            membership.save(update_fields=["status", "joined_at", "revoked_at", "updated_at"])
        owner = TenantRole.objects.get(tenant=tenant, code="TENANT_OWNER")
        MembershipRole.objects.get_or_create(membership=membership, role=owner)

        action = "creado" if created else "actualizado"
        self.stdout.write(self.style.SUCCESS(f"Superuser {username} {action}."))
