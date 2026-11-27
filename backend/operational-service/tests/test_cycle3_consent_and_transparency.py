"""Cycle 3 (PRV-010, PRV-011, PRV-012 / QG-3): Optional RUT, legal_basis, ISO TS 27560 receipts & AI Act Art. 50."""

from datetime import datetime, timezone
import unittest

from app.schemas.webchat import WEBCHAT_AI_DISCLOSURE, WebchatSessionOut
from app.services.consent_authorization_service import VALID_LEGAL_BASES, build_ts27560_consent_receipt
from app.tenant_models.consent_ledger import ContactConsentDecision
from app.tenant_models.operations import Cliente


class Cycle3ConsentAndTransparencyTests(unittest.TestCase):
    def test_prv010_cliente_rut_is_optional_and_legal_bases_are_complete(self):
        self.assertTrue(Cliente.__table__.c.rut.nullable, "clientes.rut must be nullable (PRV-010)")
        self.assertEqual(
            VALID_LEGAL_BASES,
            frozenset({"consent", "contract", "legal_obligation", "legitimate_interest"}),
        )
        cols = set(ContactConsentDecision.__table__.c.keys())
        self.assertTrue({"legal_basis", "notice_version", "notice_hash", "jurisdiction"}.issubset(cols))

    def test_prv011_iso_ts_27560_consent_receipt_structure(self):
        now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
        decision = ContactConsentDecision(
            id=101,
            client_id=55,
            channel="email",
            destination="titular@example.test",
            purpose="marketing",
            granted=True,
            effective_at=now,
            recorded_at=now,
            policy_version="v2.0",
            legal_basis="consent",
            notice_version="2026-11-v1",
            notice_hash="a" * 64,
            jurisdiction="CL",
            source="form",
        )
        receipt = build_ts27560_consent_receipt(
            decision,
            tenant_slug="acme-cl",
            controller_name="Acme SpA",
            dpo_contact_email="dpo@acme.cl",
        )
        self.assertEqual(receipt["schemaVersion"], "ISO/IEC TS 27560:2023")
        self.assertEqual(receipt["recordId"], "urn:kronflow:acme-cl:consent:101")
        self.assertEqual(receipt["piiPrincipalId"], "contact:55")
        self.assertEqual(receipt["jurisdiction"], "CL")
        self.assertEqual(receipt["piiControllers"][0]["contact"], "dpo@acme.cl")
        purpose_entry = receipt["services"][0]["purposes"][0]
        self.assertEqual(purpose_entry["purpose"], "marketing")
        self.assertEqual(purpose_entry["lawfulBasis"], "consent")
        self.assertEqual(purpose_entry["status"], "granted")
        self.assertEqual(purpose_entry["noticeVersion"], "2026-11-v1")
        self.assertEqual(purpose_entry["noticeHash"], "a" * 64)

    def test_prv012_webchat_session_exposes_eu_ai_act_art50_disclosure(self):
        now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
        session = WebchatSessionOut(
            session_token="wct_test",
            conversation_id=1,
            welcome_message="Hola",
            cursor=1,
            expires_at=now,
        )
        self.assertIn("Inteligencia Artificial", session.ai_disclosure)
        self.assertIn("Art. 50", session.ai_disclosure)
        self.assertEqual(session.ai_disclosure, WEBCHAT_AI_DISCLOSURE)


if __name__ == "__main__":
    unittest.main()
