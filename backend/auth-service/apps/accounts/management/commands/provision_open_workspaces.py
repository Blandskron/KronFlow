from django.core.management.base import BaseCommand
from requests import RequestException

from apps.tenants.models import Tenant, TenantOperationalRuntime
from apps.tenants.services import ensure_open_workspace


class Command(BaseCommand):
    help = "Provision active workspaces that predate the open-source setup."

    def handle(self, *args, **options):
        workspaces = Tenant.objects.filter(status=Tenant.Status.ACTIVE).exclude(
            operational_runtime__status__in=[TenantOperationalRuntime.Status.ACTIVE, TenantOperationalRuntime.Status.SUSPENDED]
        )
        for workspace in workspaces.iterator():
            try:
                ensure_open_workspace(workspace)
            except RequestException:
                self.stderr.write(f"Workspace {workspace.pk}: operational provisioning will be retried.")
