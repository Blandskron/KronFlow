"""Evaluate one campaign recipient against current contact and consent evidence."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


Channel = Literal["email", "whatsapp"]
Reason = Literal["eligible", "point_unavailable", "suppressed", "consent_missing", "consent_denied"]


def _as_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Campaign consent requires timestamps with a time zone")
    return value.astimezone(timezone.utc)


def _require_purpose(purpose: str) -> None:
    if not purpose or purpose != purpose.strip():
        raise ValueError("Campaign consent requires an explicit purpose")


@dataclass(frozen=True)
class ContactPointKey:
    tenant_id: int
    point_id: int
    channel: Channel


@dataclass(frozen=True)
class CampaignRecipient:
    point: ContactPointKey
    purpose: str

    def __post_init__(self) -> None:
        _require_purpose(self.purpose)


@dataclass(frozen=True)
class ContactPointStatus:
    point: ContactPointKey
    active: bool
    verified: bool


@dataclass(frozen=True)
class ConsentDecision:
    recipient: CampaignRecipient
    granted: bool
    effective_at: datetime
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "effective_at", _as_utc(self.effective_at))
        object.__setattr__(self, "recorded_at", _as_utc(self.recorded_at))


@dataclass(frozen=True)
class CampaignSuppression:
    point: ContactPointKey
    purpose: str | None
    recorded_at: datetime

    def __post_init__(self) -> None:
        if self.purpose is not None:
            _require_purpose(self.purpose)
        object.__setattr__(self, "recorded_at", _as_utc(self.recorded_at))


def campaign_eligibility(
    recipient: CampaignRecipient,
    contact_point: ContactPointStatus | None,
    decisions: Iterable[ConsentDecision],
    suppressions: Iterable[CampaignSuppression],
    *,
    now: datetime,
) -> Reason:
    """Use evidence visible at evaluation time. A denial wins an effective-time tie."""
    now = _as_utc(now)
    if (
        contact_point is None
        or contact_point.point != recipient.point
        or contact_point.active is not True
        or contact_point.verified is not True
    ):
        return "point_unavailable"

    if any(
        suppression.point == recipient.point
        and suppression.purpose in (None, recipient.purpose)
        and suppression.recorded_at <= now
        for suppression in suppressions
    ):
        return "suppressed"

    latest = max(
        (
            decision for decision in decisions
            if decision.recipient == recipient and max(decision.effective_at, decision.recorded_at) <= now
        ),
        key=lambda decision: (decision.effective_at, decision.granted is not True),
        default=None,
    )
    if latest is None:
        return "consent_missing"
    return "eligible" if latest.granted is True else "consent_denied"
