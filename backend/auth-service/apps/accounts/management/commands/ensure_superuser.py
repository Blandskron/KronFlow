import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.rbac.models import MembershipRole, TenantRole
from apps.rbac.services import seed_roles_for_tenant
from apps.tenants.models import Tenant, TenantMembership


class Command(BaseCommand):
    help = "Crea o actualiza un superuser desde variables de entorno."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", help="Defaults to DJANGO_SUPERUSER_PASSWORD.")
        parser.add_argument("--username")
        parser.add_argument("--create-only", action="store_true", help="Preserve an existing administrator.")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        username = (options.get("username") or email).strip().lower()
        password = options.get("password") or os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        User = get_user_model()

        try:
            validate_email(email)
            User._meta.get_field("username").run_validators(username)
        except ValidationError as exc:
            raise CommandError("The administrator email or username is invalid.") from exc
        if not password:
            raise CommandError("Set DJANGO_SUPERUSER_PASSWORD or pass --password.")

        user = User.objects.select_for_update().filter(username=username).first()
        created = user is None
        if user and options["create_only"]:
            if user.email.lower() != email or not (user.is_staff and user.is_superuser and user.is_active):
                raise CommandError("The bootstrap username already belongs to a different or inactive account.")
            self.stdout.write("Existing Django superuser preserved.")
            return
        if User.objects.filter(email__iexact=email).exclude(pk=user.pk if user else None).exists():
            raise CommandError("The administrator email already belongs to another account.")

        if created:
            user = User(username=username)
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user._skip_email_verification = True
        user.set_password(password)
        user.save()

        profile = user.profile
        now = timezone.now()
        profile.email_verified_at = profile.email_verified_at or now
        profile.account_activated_at = profile.account_activated_at or now
        profile.initial_password_set_at = profile.initial_password_set_at or now
        profile.save(update_fields=["email_verified_at", "account_activated_at", "initial_password_set_at", "updated_at"])

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
