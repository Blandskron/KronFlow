"""PRV-005 / QG-1: Unit tests for operational-service pre-egress PII scrubber."""

import unittest

from app.core.pii_scrubber import is_valid_chilean_rut, is_valid_luhn_pan, scrub_payload


class OperationalPiiScrubberTests(unittest.TestCase):
    def test_scrubs_nested_mcp_arguments_without_altering_non_pii(self):
        self.assertTrue(is_valid_chilean_rut("12.345.678-5"))
        self.assertFalse(is_valid_chilean_rut("12.345.678-0"))
        self.assertTrue(is_valid_luhn_pan("4111-1111-1111-1111"))
        self.assertFalse(is_valid_luhn_pan("4111-1111-1111-1119"))

        payload = {
            "resource_id": 42,
            "note": "RUT 12.345.678-5 correo user@acme.cl tel +56 9 8765 4321 card 4111-1111-1111-1111",
            "tags": ["vip", "pedido-9912"],
        }
        scrubbed, session = scrub_payload(payload)
        self.assertEqual(scrubbed["resource_id"], 42)
        self.assertEqual(scrubbed["tags"], ["vip", "pedido-9912"])
        self.assertNotIn("12.345.678-5", scrubbed["note"])
        self.assertNotIn("user@acme.cl", scrubbed["note"])
        self.assertNotIn("+56 9 8765 4321", scrubbed["note"])
        self.assertNotIn("4111-1111-1111-1111", scrubbed["note"])
        self.assertEqual(session.redaction_count, 4)


if __name__ == "__main__":
    unittest.main()
