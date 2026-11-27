import os
from pathlib import Path

import requests

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
        if local and tenant and os.getenv("FLOWKRON_DEMO_CONTEXT") == "true":
            self.seed_demo_context(tenant)
            self.seed_demo_operational_data(tenant)

    def seed_demo_context(self, tenant):
        url = f"{settings.OPERATIONAL_SERVICE_URL.rstrip('/')}/internal/tenants/{tenant.pk}/context/documents"
        headers = {"X-Internal-Token": settings.OPERATIONAL_INTERNAL_TOKEN}
        existing = requests.get(url, headers=headers, timeout=12)
        existing.raise_for_status()
        documents = existing.json()
        if isinstance(documents, dict):
            documents = documents.get("data", [])
        if documents:
            return

        guide_text = (
            "BLANDSKRON ofrece una demostración de KronFlow para gestionar consultas por WhatsApp y canales digitales. "
            "El asistente explica cómo conectar WhatsApp, cargar productos y consultar conversaciones. "
            "El catálogo, los precios y la disponibilidad se deben confirmar con el equipo. "
            "Si un cliente pide una cotización, toma nota del producto o servicio que busca y deriva la consulta."
        )
        catalog_text = (
            "Planes de referencia KronFlow (demo): Starter (hasta 5 ejecutivos, WhatsApp + CRM + RAG), "
            "Pro (hasta 25 ejecutivos, multi-agente, workflows DAG y campañas email) y Enterprise "
            "(esquema dedicado, Tool Hub + MCP bidireccional, integraciones comercio/voz y soporte SLA). "
            "Horario de atención comercial demo: lunes a viernes de 09:00 a 18:30 hora Chile."
        )
        for title, filename, text in (
            ("Guía del agente demo de BLANDSKRON", "agente-demo-blandskron.txt", guide_text),
            ("Catálogo y planes de referencia KronFlow", "catalogo-servicios-kronflow.md", catalog_text),
        ):
            result = requests.post(url, headers=headers, timeout=12, json={
                "tenant_id": str(tenant.pk),
                "title": title,
                "filename": filename,
                "raw_text": text,
                "chunks": [{"chunk_index": 0, "content": text, "token_count": len(text.split())}],
            })
            result.raise_for_status()

    def seed_demo_operational_data(self, tenant):
        url = f"{settings.OPERATIONAL_SERVICE_URL.rstrip('/')}/internal/tenants/{tenant.pk}/demo-seed"
        headers = {"X-Internal-Token": settings.OPERATIONAL_INTERNAL_TOKEN}
        result = requests.post(url, headers=headers, timeout=20)
        result.raise_for_status()
