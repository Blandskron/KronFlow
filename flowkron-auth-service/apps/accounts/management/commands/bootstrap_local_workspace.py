import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.tenants.models import Tenant, TenantOperationalRuntime
from apps.tenants.services import provision_operational_runtime


class Command(BaseCommand):
    help = "Set up the initial administrator and, on a fresh local install, the BLANDSKRON workspace."

    def add_arguments(self, parser):
        parser.add_argument("--explicit", action="store_true", help="Use the administrator credentials from the environment.")

    def handle(self, *args, **options):
        explicit = options["explicit"]
        local = settings.DEBUG and os.getenv("FLOWKRON_BIND_HOST") == "127.0.0.1"
        if not local and not explicit:
            raise CommandError("Local workspace setup requires debug mode and a loopback bind.")

        with transaction.atomic():
            fresh_install = not get_user_model().objects.exists() and not Tenant.objects.exists()
            if explicit or fresh_install:
                email = os.getenv("DJANGO_SUPERUSER_EMAIL") or ("" if explicit else "admin@example.com")
                username = os.getenv("DJANGO_SUPERUSER_USERNAME") or email
                if explicit:
                    password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
                    if not email or not password:
                        raise CommandError("CREATE_SUPERUSER requires DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD.")
                else:
                    password = Path(os.environ["FLOWKRON_BOOTSTRAP_PASSWORD_FILE"]).read_text(encoding="utf-8").strip()
                call_command("ensure_superuser", email=email, username=username, password=password, create_only=True)
                if fresh_install and local:
                    Tenant.objects.filter(slug=settings.IAM_PLATFORM_TENANT_SLUG).update(
                        plan=Tenant.Plan.STARTER,
                        subscription_status=Tenant.SubscriptionStatus.ACTIVE,
                        subscription_provider="flowkron-local",
                    )

        if not local:
            return

        tenant = Tenant.objects.filter(
            slug=settings.IAM_PLATFORM_TENANT_SLUG,
            status=Tenant.Status.ACTIVE,
            subscription_status=Tenant.SubscriptionStatus.ACTIVE,
            subscription_provider="flowkron-local",
        ).first()
        if tenant and not TenantOperationalRuntime.objects.filter(
            tenant=tenant,
            status__in=[TenantOperationalRuntime.Status.ACTIVE, TenantOperationalRuntime.Status.SUSPENDED],
        ).exists():
            provision_operational_runtime(tenant)
