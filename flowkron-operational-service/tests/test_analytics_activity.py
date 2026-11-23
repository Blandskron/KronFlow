from datetime import date, datetime, timezone
from unittest.mock import patch
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente, Lead, Message
from test_message_identity import PostgresCase
import test_turn_recovery


class AnalyticsActivityTests(PostgresCase):
    def test_report_validates_calendar_and_counts_only_the_authenticated_workspace(self):
        tenant, other = self.tenant(), self.tenant()
        now = datetime(2026, 11, 3, 15, tzinfo=timezone.utc)
        stamps = [datetime.fromisoformat(f"2026-11-{day}T{clock}+00:00") for day, clock in (
            ("01", "03:59:00"),  # before midnight in New York
            ("01", "04:00:00"),  # local midnight
            ("01", "05:30:00"),  # first 01:30
            ("01", "06:30:00"),  # second 01:30 after the clock rolls back
            ("03", "14:59:00"),
            ("03", "15:00:00"),  # excluded at the observation cutoff
        )]
        for workspace in (tenant, other):
            with Session(self.engine.execution_options(**tenant_exec_options(workspace.schema_name))) as db:
                db.add(Lead(creado_en=stamps[1], cliente=Cliente(rut="synthetic", nombre="Synthetic", creado_en=stamps[1])))
                for index, stamp in enumerate(stamps):
                    outbound = index in (3, 4)
                    db.add(Message(whatsapp_id="synthetic", mensaje="Synthetic", creado_en=stamp,
                                   direction="outbound" if outbound else "inbound", rol="agente" if outbound else "usuario"))
                if workspace == other:
                    db.add(Message(whatsapp_id="extra", mensaje="Synthetic", creado_en=stamps[1],
                                   direction="inbound", rol="usuario"))
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
        path = "/api/v1/analytics/activity?"
        query = {"start_date": "2026-11-01", "end_date": "2026-11-03", "time_zone": "America/New_York"}

        def report(**changes):
            return test_turn_recovery.TurnRecoveryTests.http(
                self, "GET", path + urlencode(query | changes), headers={"X-Tenant-ID": "813"},
            )

        self.assertEqual(report()[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "user-test", 812, None, [], permissions, {}, {},
        )
        self.assertEqual(report()[0], 403)
        permissions.append("users.read")
        with patch("app.services.analytics_service.datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            for changes in ({"time_zone": "Invalid/Zone"}, {"time_zone": "-03:00"},
                            {"start_date": "2026-11-04"}, {"start_date": "2026-10-01"}, {"end_date": "2026-11-04"}):
                with self.subTest(changes=changes):
                    self.assertEqual(report(**changes)[0], 422)

            status, response, _ = report()
            self.assertEqual(status, 200, response)
            self.assertEqual(response["meta"]["tenant_id"], "812")
            payload = response["data"]
            self.assertEqual(payload["partial_day"], "2026-11-03")
            self.assertEqual(datetime.fromisoformat(payload["as_of"]), now)
            zero = {"contacts_created": 0, "leads_created": 0, "inbound_messages": 0, "outbound_messages": 0}
            self.assertEqual(payload["days"], [
                zero | {"day": "2026-11-01", "contacts_created": 1, "leads_created": 1,
                        "inbound_messages": 2, "outbound_messages": 1},
                zero | {"day": "2026-11-02"},
                zero | {"day": "2026-11-03", "outbound_messages": 1},
            ])
            self.assertEqual(payload["totals"], {
                "contacts_created": 1, "leads_created": 1, "inbound_messages": 2, "outbound_messages": 2,
            })
            self.assertIsNone(report(end_date=date(2026, 11, 2).isoformat())[1]["data"]["partial_day"])
