"""Cycle 5 (PRV-017, PRV-018, PRV-019 / QG-5): Retention policies, schema purge, PII log filter & tombstones."""

import logging
import unittest

from app.core.pii_log_filter import PiiRedactingLogFilter, sanitize_log_text
from app.main import app
from app.public_models.erasure_tombstone import PrivacyErasureTombstone
from app.services.privacy_case_service import _tombstone_hash
from app.tenant_models.privacy_lifecycle import TenantRetentionPolicy


class Cycle5LifecycleTests(unittest.TestCase):
    def test_prv017_prv018_prv019_models_routes_and_tombstone_hashes(self):
        # PRV-017: TenantRetentionPolicy columns and OpenAPI routes.
        ret_cols = set(TenantRetentionPolicy.__table__.c.keys())
        self.assertTrue(
            {"messages_retention_days", "memory_retention_days", "legal_hold", "last_swept_at"}.issubset(ret_cols)
        )
        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/operational/retention-policy", paths)
        self.assertIn("get", paths["/api/v1/operational/retention-policy"])
        self.assertIn("put", paths["/api/v1/operational/retention-policy"])

        # PRV-018: Internal tenant schema purge endpoint registered.
        self.assertIn("/internal/tenants/{tenant_id}/purge", paths)
        self.assertIn("delete", paths["/internal/tenants/{tenant_id}/purge"])

        # PRV-019: Tombstones store irreversible 64-char SHA-256 hashes (no raw PII).
        tomb_cols = set(PrivacyErasureTombstone.__table__.c.keys())
        self.assertTrue({"auth_tenant_id", "schema_name", "identifier_kind", "subject_hash"}.issubset(tomb_cols))
        h1 = _tombstone_hash("tenant_demo", "rut", "12.345.678-5")
        h2 = _tombstone_hash("tenant_demo", "rut", "12345678-5")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)
        self.assertNotIn("12345678", h1)

    def test_prv019_operational_log_filter_masks_pii_and_tokens(self):
        raw = "Contact ana@example.cl RUT 12.345.678-5 auth Bearer synthetic_token_1234567890"
        cleaned = sanitize_log_text(raw)
        self.assertNotIn("ana@example.cl", cleaned)
        self.assertNotIn("12.345.678-5", cleaned)
        self.assertNotIn("synthetic_token_1234567890", cleaned)

        filt = PiiRedactingLogFilter()
        record = logging.LogRecord("op", logging.INFO, __file__, 1, "Email %s", ("bob@example.cl",), None)
        self.assertTrue(filt.filter(record))
        self.assertEqual(record.getMessage(), "Email [REDACTED_EMAIL]")


if __name__ == "__main__":
    unittest.main()
