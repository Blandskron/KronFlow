from datetime import date, datetime

from pydantic import BaseModel


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

