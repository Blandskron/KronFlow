from django.core.management.base import BaseCommand

from apps.rbac.services import seed_permissions
from apps.security.services import MACHINE_SCOPES, create_service_account, get_active_signing_key
from apps.security.models import ServiceAccount


class Command(BaseCommand):
    help = "Inicializa scopes internos, service accounts base y primera clave de firma."

    def handle(self, *args, **options):
        seed_permissions()
        key = get_active_signing_key()
        for name in ["auth-service", "rag-service"]:
            if not ServiceAccount.objects.filter(name=name).exists():
                account = create_service_account(name=name, scopes=MACHINE_SCOPES)
                self.stdout.write(f"{name} creado con client_id={account.client_id}. Rote el secreto desde el flujo administrativo.")
        self.stdout.write(self.style.SUCCESS(f"IAM avanzado inicializado con signing key {key.kid}."))
