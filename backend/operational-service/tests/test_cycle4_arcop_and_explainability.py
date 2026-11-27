"""Cycle 4 (PRV-013, PRV-014, PRV-016 / QG-4): Portable export, ARCOP+B rights & scoring explainability tests."""

import unittest

from app.main import app
from app.schemas.privacy_case import (
    PrivacyCaseCreateIn,
    PrivacyCaseExportOut,
    PrivacyRectifyIn,
    PrivacyRestrictIn,
)
from app.tenant_models.operations import Cliente, Lead, SolicitudDerecho


class Cycle4ArcopAndExplainabilityTests(unittest.TestCase):
    def test_prv013_prv014_prv016_models_and_schemas_cover_arcop_b_and_explainability(self):
        # PRV-013: Multichannel DSAR creation (contact_id / email / whatsapp_id) & portable export fields.
        req_email = PrivacyCaseCreateIn(kind="portabilidad", email="titular@example.test")
        self.assertEqual(req_email.kind, "portabilidad")
        req_block = PrivacyCaseCreateIn(kind="bloqueo", contact_id=42)
        self.assertEqual(req_block.kind, "bloqueo")
        self.assertTrue({"client_id", "subject_email"}.issubset(set(SolicitudDerecho.__table__.c.keys())))
        export_fields = set(PrivacyCaseExportOut.model_fields.keys())
        self.assertTrue({"messages", "voice_transcripts", "commerce_orders", "consent_receipts"}.issubset(export_fields))

        # PRV-014: Rectification & processing_restricted columns/schemas.
        self.assertTrue({"processing_restricted", "processing_restricted_reason"}.issubset(set(Cliente.__table__.c.keys())))
        rect = PrivacyRectifyIn(nombre="Corregido", email="nuevo@example.test")
        self.assertEqual(rect.nombre, "Corregido")
        restr = PrivacyRestrictIn(restricted=True, reason="impugnacion_titular")
        self.assertTrue(restr.restricted)

        # PRV-016: Lead scoring explainability and human review columns.
        self.assertTrue(
            {"score_factors_json", "human_review_requested", "human_review_reason"}.issubset(set(Lead.__table__.c.keys()))
        )

    def test_cycle4_routes_registered_in_openapi(self):
        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/operational/privacy-cases", paths)
        self.assertIn("post", paths["/api/v1/operational/privacy-cases"])
        self.assertIn("/api/v1/operational/privacy-cases/{case_id}/rectify", paths)
        self.assertIn("/api/v1/operational/privacy-cases/{case_id}/restrict", paths)
        self.assertIn("/api/v1/leads/{lead_id}/score-explanation", paths)
        self.assertIn("/api/v1/leads/{lead_id}/human-review", paths)


if __name__ == "__main__":
    unittest.main()
