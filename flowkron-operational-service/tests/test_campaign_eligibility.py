import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.services.campaign_eligibility import (
    CampaignRecipient,
    CampaignSuppression,
    ConsentDecision,
    ContactPointKey,
    ContactPointStatus,
    campaign_eligibility,
)
from scripts.demo_campaign_eligibility import run_demo


class CampaignEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        self.earlier = self.now - timedelta(seconds=1)
        self.key = ContactPointKey(tenant_id=1, point_id=42, channel="email")
        self.recipient = CampaignRecipient(self.key, "marketing")
        self.point = ContactPointStatus(self.key, active=True, verified=True)
        self.granted = ConsentDecision(self.recipient, True, self.earlier, self.earlier)

    def test_only_exact_scope_provides_consent(self):
        variants = (
            replace(self.recipient, purpose="servicio"),
            replace(self.recipient, point=replace(self.key, tenant_id=2)),
            replace(self.recipient, point=replace(self.key, point_id=43)),
            replace(self.recipient, point=replace(self.key, channel="whatsapp")),
        )
        for other in variants:
            with self.subTest(other=other):
                decision = replace(self.granted, recipient=other)
                self.assertEqual(campaign_eligibility(self.recipient, self.point, [decision], [], now=self.now),
                                 "consent_missing")
        self.assertEqual(campaign_eligibility(self.recipient, self.point, [self.granted], [], now=self.now),
                         "eligible")

    def test_point_must_be_current_verified_and_exact(self):
        for point in (None, replace(self.point, active=False), replace(self.point, verified=False),
                      replace(self.point, point=replace(self.key, point_id=43))):
            with self.subTest(point=point):
                self.assertEqual(campaign_eligibility(self.recipient, point, [self.granted], [], now=self.now),
                                 "point_unavailable")

    def test_latest_effective_decision_wins_and_ties_deny_in_both_orders(self):
        denied = replace(self.granted, granted=False)
        renewal = replace(self.granted, effective_at=self.now, recorded_at=self.now)
        for evidence in ([denied, self.granted], [self.granted, denied]):
            self.assertEqual(campaign_eligibility(self.recipient, self.point, evidence, [], now=self.now),
                             "consent_denied")
        self.assertEqual(campaign_eligibility(self.recipient, self.point, [renewal, denied], [], now=self.now),
                         "eligible")

    def test_evidence_must_be_effective_and_known(self):
        later = self.now + timedelta(seconds=1)
        for decision in (replace(self.granted, effective_at=later), replace(self.granted, recorded_at=later)):
            self.assertEqual(campaign_eligibility(self.recipient, self.point, [decision], [], now=self.now),
                             "consent_missing")
            self.assertEqual(campaign_eligibility(self.recipient, self.point, [decision], [], now=later),
                             "eligible")

    def test_equal_instants_with_different_offsets_deny_on_tie(self):
        local_offset = timezone(timedelta(hours=-3))
        denial = replace(self.granted, granted=False, effective_at=self.earlier.astimezone(local_offset))
        self.assertEqual(campaign_eligibility(self.recipient, self.point, [self.granted, denial], [],
                                              now=self.now.astimezone(local_offset)), "consent_denied")

    def test_rejects_absent_purpose(self):
        for purpose in ("", " ", "marketing "):
            with self.subTest(purpose=purpose), self.assertRaises(ValueError):
                replace(self.recipient, purpose=purpose)
            with self.subTest(suppression_purpose=purpose), self.assertRaises(ValueError):
                CampaignSuppression(self.key, purpose, self.now)

    def test_suppression_blocks_authorized_point_only_within_scope(self):
        all_purposes = CampaignSuppression(self.key, None, self.now)
        for suppression in (all_purposes, replace(all_purposes, purpose="marketing")):
            self.assertEqual(campaign_eligibility(self.recipient, self.point, [self.granted], [suppression],
                                                  now=self.now), "suppressed")
        irrelevant = [
            replace(all_purposes, purpose="servicio"),
            replace(all_purposes, point=replace(self.key, tenant_id=2)),
            replace(all_purposes, point=replace(self.key, channel="whatsapp")),
            replace(all_purposes, recorded_at=self.now + timedelta(seconds=1)),
        ]
        self.assertEqual(campaign_eligibility(self.recipient, self.point, [self.granted], irrelevant, now=self.now),
                         "eligible")

    def test_rejects_timestamps_without_time_zone(self):
        naive = self.now.replace(tzinfo=None)
        with self.assertRaises(ValueError):
            replace(self.granted, effective_at=naive)
        with self.assertRaises(ValueError):
            replace(self.granted, recorded_at=naive)
        with self.assertRaises(ValueError):
            CampaignSuppression(self.key, None, naive)
        with self.assertRaises(ValueError):
            campaign_eligibility(self.recipient, self.point, [], [], now=naive)

    def test_demo_rechecks_the_approved_snapshot_at_dispatch(self):
        result = run_demo()
        self.assertEqual(result["environment"], "synthetic")
        self.assertEqual(result["stub_accepted"], 2)
        self.assertEqual(
            {row["scenario"]: (row["approval"], row["dispatch"]) for row in result["cases"]},
            {
                "opt_in_vigente": ("eligible", "stub_accepted"),
                "email_verificado_sin_opt_in": ("consent_missing", "outside_snapshot"),
                "opt_in_para_otra_finalidad": ("consent_missing", "outside_snapshot"),
                "opt_in_de_otro_canal": ("consent_missing", "outside_snapshot"),
                "opt_in_de_otra_empresa": ("consent_missing", "outside_snapshot"),
                "baja_despues_de_aprobar": ("eligible", "consent_denied"),
                "supresion_del_canal_despues_de_aprobar": ("eligible", "suppressed"),
                "verificacion_perdida": ("eligible", "point_unavailable"),
                "opt_in_despues_de_aprobar": ("consent_missing", "outside_snapshot"),
                "denegacion_en_el_mismo_instante": ("consent_denied", "outside_snapshot"),
                "renovacion_posterior_a_una_baja_recibida_tarde": ("eligible", "stub_accepted"),
            },
        )
