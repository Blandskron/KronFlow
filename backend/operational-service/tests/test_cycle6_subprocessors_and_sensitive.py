"""Cycle 6 (PRV-020 & PRV-021 / QG-6): Subprocessor registry and sensitive/minor data detection tests."""

import unittest

from app.core.pii_scrubber import detect_sensitive_data
from app.main import app
from app.services.subprocessor_service import SUBPROCESSOR_CATALOG
from app.tenant_models.privacy_lifecycle import TenantSubprocessorApproval


class Cycle6SubprocessorsAndSensitiveDataTests(unittest.TestCase):
    def test_prv020_subprocessor_registry_catalog_model_and_routes(self):
        expected_providers = {"groq", "resend", "meta", "twilio", "shopify", "mercadopago", "google", "hubspot", "remote_mcp"}
        self.assertTrue(expected_providers.issubset(set(SUBPROCESSOR_CATALOG.keys())))
        cols = set(TenantSubprocessorApproval.__table__.c.keys())
        self.assertTrue({"provider_key", "jurisdiction", "subprocessor_list_version", "approved", "approved_by"}.issubset(cols))
        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/operational/subprocessors", paths)
        self.assertIn("/api/v1/operational/subprocessors/{provider_key}", paths)

    def test_prv021_detects_health_minor_and_financial_card_sensitive_data(self):
        health = detect_sensitive_data("Necesito cobertura en mi Isapre para una cirugía.")
        self.assertTrue(health["has_sensitive_data"])
        self.assertIn("health", health["categories"])

        minor = detect_sensitive_data("Hola, tengo 15 años y soy menor de edad.")
        self.assertTrue(minor["has_sensitive_data"])
        self.assertIn("minor", minor["categories"])

        card = detect_sensitive_data("Mi tarjeta es 4111-1111-1111-1111")
        self.assertTrue(card["has_sensitive_data"])
        self.assertIn("financial_card", card["categories"])

        clean = detect_sensitive_data("Hola, quiero cotizar el plan Starter para mi empresa.")
        self.assertFalse(clean["has_sensitive_data"])
        self.assertEqual(clean["categories"], [])


if __name__ == "__main__":
    unittest.main()
