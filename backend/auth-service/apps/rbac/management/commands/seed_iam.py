from django.core.management.base import BaseCommand

from apps.rbac.services import seed_permissions, seed_roles_for_tenant
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Carga permisos base y roles sistema para todos los tenants existentes."

    def handle(self, *args, **options):
        seed_permissions()
        for tenant in Tenant.objects.all():
            seed_roles_for_tenant(tenant)
        self.stdout.write(self.style.SUCCESS("IAM seed completado."))
