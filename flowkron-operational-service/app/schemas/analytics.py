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

