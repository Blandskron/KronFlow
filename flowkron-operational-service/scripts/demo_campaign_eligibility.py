"""Exercise campaign consent from approval to simulated dispatch using synthetic IDs."""

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from app.services.campaign_eligibility import (
    CampaignRecipient,
    CampaignSuppression,
    ConsentDecision,
    ContactPointKey,
    ContactPointStatus,
    campaign_eligibility,
)


@dataclass(frozen=True)
class DemoRecipient:
    scenario: str
    request: CampaignRecipient
    approved_point: ContactPointStatus | None
    dispatch_point: ContactPointStatus | None
    decisions: tuple[ConsentDecision, ...] = ()
    suppressions: tuple[CampaignSuppression, ...] = ()


def run_demo() -> dict:
    approval_at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    dispatch_at = approval_at + timedelta(minutes=2)
    before_approval = approval_at - timedelta(minutes=1)
    after_approval = approval_at + timedelta(minutes=1)

    def candidate(number: int, scenario: str) -> DemoRecipient:
        key = ContactPointKey(tenant_id=1, point_id=number, channel="email")
        recipient = CampaignRecipient(key, "marketing")
        point = ContactPointStatus(key, active=True, verified=True)
        return DemoRecipient(scenario, recipient, point, point)

    def grant(row: DemoRecipient) -> ConsentDecision:
        return ConsentDecision(row.request, True, before_approval, before_approval)

    eligible = candidate(1, "opt_in_vigente")
    no_opt_in = candidate(2, "email_verificado_sin_opt_in")
    other_purpose = candidate(3, "opt_in_para_otra_finalidad")
    other_channel = candidate(4, "opt_in_de_otro_canal")
    other_tenant = candidate(5, "opt_in_de_otra_empresa")
    withdrawn = candidate(6, "baja_despues_de_aprobar")
    suppressed = candidate(7, "supresion_del_canal_despues_de_aprobar")
    unverified = candidate(8, "verificacion_perdida")
    new_opt_in = candidate(9, "opt_in_despues_de_aprobar")
    same_second = candidate(10, "denegacion_en_el_mismo_instante")
    renewed = candidate(11, "renovacion_posterior_a_una_baja_recibida_tarde")

    cases = (
        replace(eligible, decisions=(grant(eligible),)),
        no_opt_in,
        replace(other_purpose, decisions=(replace(
            grant(other_purpose), recipient=replace(other_purpose.request, purpose="servicio"),
        ),)),
        replace(other_channel, decisions=(replace(
            grant(other_channel), recipient=replace(
                other_channel.request, point=replace(other_channel.request.point, channel="whatsapp"),
            ),
        ),)),
        replace(other_tenant, decisions=(replace(
            grant(other_tenant), recipient=replace(
                other_tenant.request, point=replace(other_tenant.request.point, tenant_id=2),
            ),
        ),)),
        replace(withdrawn, decisions=(
            grant(withdrawn), ConsentDecision(withdrawn.request, False, after_approval, after_approval),
        )),
        replace(suppressed, decisions=(grant(suppressed),), suppressions=(
            CampaignSuppression(suppressed.request.point, None, after_approval),
        )),
        replace(unverified, decisions=(grant(unverified),), dispatch_point=ContactPointStatus(
            unverified.request.point, active=True, verified=False,
        )),
        replace(new_opt_in, decisions=(ConsentDecision(new_opt_in.request, True, after_approval, after_approval),)),
        replace(same_second, decisions=(grant(same_second), replace(grant(same_second), granted=False))),
        replace(renewed, decisions=(
            grant(renewed),
            ConsentDecision(renewed.request, False, before_approval - timedelta(seconds=1), after_approval),
        )),
    )

    approvals = {
        row.scenario: campaign_eligibility(
            row.request, row.approved_point, row.decisions, row.suppressions, now=approval_at,
        )
        for row in cases
    }
    snapshot = tuple(row for row in cases if approvals[row.scenario] == "eligible")
    dispatch_results: dict[str, str] = {}
    for row in snapshot:
        current = campaign_eligibility(
            row.request, row.dispatch_point, row.decisions, row.suppressions, now=dispatch_at,
        )
        dispatch_results[row.scenario] = "stub_accepted" if current == "eligible" else current
    return {
        "environment": "synthetic",
        "stub_accepted": sum(result == "stub_accepted" for result in dispatch_results.values()),
        "cases": [
            {
                "scenario": row.scenario,
                "approval": approvals[row.scenario],
                "dispatch": dispatch_results.get(row.scenario, "outside_snapshot"),
            }
            for row in cases
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=True, indent=2))
