from datetime import datetime, timezone
from urllib.parse import urlencode

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
        for workspace, contacts in (
            (tenant, (("Contacto 100%", "web", "+56 (9) 1234-5678"), ("Contacto nuevo", "whatsapp_directo", None))),
            (other, (("Contacto ajeno", "origen_ajeno", "56912345678"),)),
        ):
            with Session(self.engine.execution_options(**tenant_exec_options(workspace.schema_name))) as db:
                db.add_all([
                    Cliente(id=index, rut=f"synthetic-{index}", nombre=name, creado_en=created_at,
                            canal_origen=source, telefono=phone,
                            email="contact@example.test" if index == 1 else None)
                    for index, (name, source, phone) in enumerate(contacts, start=1 if workspace == tenant else 31)
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
        self.assertEqual(http(self, "GET", path + "/1")[0], 403)
        self.assertEqual(http(self, "GET", path + "/sources")[0], 403)
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

        _, sources, _ = http(self, "GET", path + "/sources", headers={"X-Tenant-ID": "813"})
        self.assertEqual(sources["data"], ["web", "whatsapp_directo"])
        _, filtered, _ = http(self, "GET", path + "?source=web")
        self.assertEqual(filtered["data"]["items"][0]["full_name"], "Contacto 100%")
        self.assertEqual(filtered["data"]["total"], 1)
        _, hidden, _ = http(self, "GET", path + "?source=origen_ajeno")
        self.assertEqual(hidden["data"]["total"], 0)

        for query in ("56912345678", "+56 9 1234 5678"):
            _, phone_match, _ = http(self, "GET", path + "?" + urlencode({"q": query, "source": "web"}))
            self.assertEqual(phone_match["data"]["total"], 1)
            self.assertEqual(phone_match["data"]["items"][0]["phone"], "+56 (9) 1234-5678")

        status, detail, _ = http(self, "GET", path + "/1", headers={"X-Tenant-ID": "813"})
        self.assertEqual(status, 200)
        self.assertEqual(detail["data"], filtered["data"]["items"][0])
        self.assertEqual(http(self, "GET", path + "/31", headers={"X-Tenant-ID": "813"})[0], 404)
        self.assertEqual(http(self, "GET", path + "/0")[0], 422)
