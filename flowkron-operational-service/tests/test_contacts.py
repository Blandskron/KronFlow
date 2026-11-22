from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente
from test_message_identity import PostgresCase
import test_turn_recovery


class ContactDirectoryTests(PostgresCase):
    def test_search_pagination_and_access_are_tenant_scoped(self):
        tenant, other = self.tenant(), self.tenant()
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for workspace, names in ((tenant, ("Contacto 100%", "Contacto nuevo")), (other, ("Contacto ajeno",))):
            with Session(self.engine.execution_options(**tenant_exec_options(workspace.schema_name))) as db:
                db.add_all([
                    Cliente(rut=f"synthetic-{index}", nombre=name, creado_en=created_at,
                            email="contact@example.test" if index == 1 else None)
                    for index, name in enumerate(names, start=1)
                ])
                db.commit()

        with Session(self.engine) as db:
            for tenant_id, workspace in ((812, tenant), (813, other)):
                db.add(TenantRuntime(auth_tenant_id=tenant_id, schema_name=workspace.schema_name,
                                     tenant_slug=workspace.tenant_slug, tenant_code=workspace.tenant_code,
                                     ingest_key_hash="unused", status="active", plan="free"))
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        permissions = []
        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)
        http = test_turn_recovery.TurnRecoveryTests.http
        path = "/api/v1/contacts"
        self.assertEqual(http(self, "GET", path)[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "user-test", 812, None, [], permissions, {}, {},
        )
        self.assertEqual(http(self, "GET", path)[0], 403)
        permissions.append("users.read")

        status, first, _ = http(self, "GET", path + "?limit=1", headers={"X-Tenant-ID": "813"})
        self.assertEqual(status, 200)
        self.assertEqual(first["meta"]["tenant_id"], "812")
        self.assertEqual(first["data"]["total"], 2)
        self.assertEqual(first["data"]["items"][0]["full_name"], "Contacto nuevo")
        _, second, _ = http(self, "GET", path + "?limit=1&offset=1")
        self.assertEqual(second["data"]["items"][0]["full_name"], "Contacto 100%")

        _, search, _ = http(self, "GET", path + "?q=100%25")
        self.assertEqual(search["data"]["total"], 1)
        self.assertEqual(set(search["data"]["items"][0]), {"id", "full_name", "email", "phone", "source", "created_at"})
        _, email, _ = http(self, "GET", path + "?q=EXAMPLE.TEST")
        self.assertEqual(email["data"]["total"], 1)
        self.assertEqual(http(self, "GET", path + "?q=" + "x" * 121)[0], 422)
