from datetime import UTC, datetime, timedelta
from pathlib import Path
import unittest

from app.main import app
from app.services.audit_event_catalog import EVENTS
from app.services.privacy_case_service import (
    GENESIS_CLEANUP_HASH,
    compute_cleanup_entry_hash,
    verify_cleanup_hash_chain,
)
from app.services.security_incident_service import compute_incident_sla_deadlines


REPO_ROOT = Path(__file__).resolve().parents[3]


class Cycle7GovernanceAndIncidentsTests(unittest.TestCase):
    def test_cleanup_hash_chain_detects_tampering(self):
        t0 = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
        h1 = compute_cleanup_entry_hash(
            GENESIS_CLEANUP_HASH,
            fecha_ejecucion=t0,
            mensajes_eliminados=10,
            clientes_anonimizados=1,
            solicitudes_eliminadas=1,
            estado="exitoso",
            detalle={"case_id": 1},
        )
        h2 = compute_cleanup_entry_hash(
            h1,
            fecha_ejecucion=t0 + timedelta(minutes=5),
            mensajes_eliminados=5,
            clientes_anonimizados=0,
            solicitudes_eliminadas=0,
            estado="exitoso",
            detalle={"retention_days": 90},
        )
        h3 = compute_cleanup_entry_hash(
            h2,
            fecha_ejecucion=t0 + timedelta(minutes=10),
            mensajes_eliminados=2,
            clientes_anonimizados=0,
            solicitudes_eliminadas=0,
            estado="exitoso",
            detalle={"retention_days": 30},
        )
        entries = [
            {
                "id": 1,
                "prev_hash": GENESIS_CLEANUP_HASH,
                "entry_hash": h1,
                "fecha_ejecucion": t0,
                "mensajes_eliminados": 10,
                "clientes_anonimizados": 1,
                "solicitudes_eliminadas": 1,
                "estado": "exitoso",
                "detalle": {"case_id": 1},
            },
            {
                "id": 2,
                "prev_hash": h1,
                "entry_hash": h2,
                "fecha_ejecucion": t0 + timedelta(minutes=5),
                "mensajes_eliminados": 5,
                "clientes_anonimizados": 0,
                "solicitudes_eliminadas": 0,
                "estado": "exitoso",
                "detalle": {"retention_days": 90},
            },
            {
                "id": 3,
                "prev_hash": h2,
                "entry_hash": h3,
                "fecha_ejecucion": t0 + timedelta(minutes=10),
                "mensajes_eliminados": 2,
                "clientes_anonimizados": 0,
                "solicitudes_eliminadas": 0,
                "estado": "exitoso",
                "detalle": {"retention_days": 30},
            },
        ]
        ok = verify_cleanup_hash_chain(entries)
        self.assertTrue(ok["valid"])
        self.assertEqual(ok["checked"], 3)
        self.assertIsNone(ok["broken_entry_id"])

        # Tamper with row 2 count without recomputing chain
        entries[1]["mensajes_eliminados"] = 999
        tampered = verify_cleanup_hash_chain(entries)
        self.assertFalse(tampered["valid"])
        self.assertEqual(tampered["broken_entry_id"], 2)
        self.assertEqual(tampered["reason"], "entry_hash_mismatch")

    def test_security_incident_sla_deadlines_3h_and_72h(self):
        detected = datetime(2026, 11, 27, 15, 30, tzinfo=UTC)
        csirt_due, authority_due = compute_incident_sla_deadlines(detected)
        self.assertEqual(csirt_due, detected + timedelta(hours=3))
        self.assertEqual(authority_due, detected + timedelta(hours=72))

    def test_audit_catalog_and_openapi_register_cycle7_routes(self):
        self.assertIn("privacy.pii.accessed", EVENTS)
        self.assertIn("security.incident.opened", EVENTS)
        self.assertIn("security.incident.updated", EVENTS)

        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/operational/log-limpiezas/verify-chain", paths)
        self.assertIn("/api/v1/operational/security-incidents", paths)
        self.assertIn("/api/v1/operational/security-incidents/{incident_id}", paths)

    def test_security_runbook_and_dpia_template_exist(self):
        security_md = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("Ley 21.663", security_md)
        self.assertIn("3 hours", security_md)
        self.assertIn("72 hours", security_md)
        self.assertIn("GDPR Art. 33", security_md)

        dpia_md = (REPO_ROOT / "compliance" / "DPIA_TEMPLATE_ISO29134.md").read_text(encoding="utf-8")
        self.assertIn("ISO/IEC 29134:2023", dpia_md)
        self.assertIn("ISO/IEC 27701:2025", dpia_md)


if __name__ == "__main__":
    unittest.main()
