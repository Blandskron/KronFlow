from datetime import date, datetime

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    total_leads: int
    cold_leads: int
    warm_leads: int
    hot_leads: int
    open_conversations: int
    requires_human: int
    messages_today: int
    messages_last_7_days: int


class ActivityCounts(BaseModel):
    contacts_created: int = 0
    leads_created: int = 0
    inbound_messages: int = 0
    outbound_messages: int = 0


class ActivityDay(ActivityCounts):
    day: date


class AnalyticsActivity(BaseModel):
    start_date: date
    end_date: date
    time_zone: str
    as_of: datetime
    partial_day: date | None
    totals: ActivityCounts
    days: list[ActivityDay]


class PipelineKpis(BaseModel):
    open_opportunities: int = 0
    won_opportunities: int = 0
    lost_opportunities: int = 0
    won_amount_by_currency: dict[str, str] = {}
    win_rate: float | None = None


class CampaignKpis(BaseModel):
    total_campaigns: int = 0
    recipients_queued: int = 0
    recipients_accepted: int = 0
    recipients_delivered: int = 0
    recipients_suppressed: int = 0
    recipients_bounced: int = 0
    recipients_unsubscribed: int = 0
    delivery_rate: float | None = None


class EventCoverageKpis(BaseModel):
    total_domain_events: int = 0
    event_counts_by_type: dict[str, int] = {}
    last_event_id: int = 0


class GovernanceKpis(BaseModel):
    open_privacy_cases: int = 0
    pending_ai_proposals: int = 0
    executed_ai_proposals: int = 0


class AIUsageKpis(BaseModel):
    days: int = 30
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost_usd: str = "0"
    avg_latency_ms: float = 0.0


class WorkflowKpis(BaseModel):
    active_workflows: int = 0
    runs_running: int = 0
    runs_waiting: int = 0
    runs_completed: int = 0
    runs_failed: int = 0
    runs_cancelled: int = 0


class CommerceKpis(BaseModel):
    total_orders: int = 0
    paid_orders: int = 0
    discrepancy_orders: int = 0
    confirmed_gross_by_currency: dict[str, int] = {}
    refunded_by_currency: dict[str, int] = {}
    confirmed_net_by_currency: dict[str, int] = {}


class VoiceKpis(BaseModel):
    total_calls: int = 0
    completed_calls: int = 0
    transferred_calls: int = 0
    no_answer_calls: int = 0
    total_billable_seconds: int = 0
    total_estimated_cost_usd: str = "0"


class AnalyticsKpisOut(BaseModel):
    as_of: datetime
    pipeline: PipelineKpis
    campaigns: CampaignKpis
    events: EventCoverageKpis
    governance: GovernanceKpis
    ai_usage: AIUsageKpis = Field(default_factory=AIUsageKpis)
    workflows: WorkflowKpis = Field(default_factory=WorkflowKpis)
    commerce: CommerceKpis = Field(default_factory=CommerceKpis)
    voice: VoiceKpis = Field(default_factory=VoiceKpis)


