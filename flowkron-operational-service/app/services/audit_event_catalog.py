from dataclasses import dataclass


@dataclass(frozen=True)
class EventProjection:
    event_type: str
    reference: str
    transition: str | None = None


EVENTS = {
    "crm.contact.created": EventProjection("contact.created", "contact_id"),
    "crm.contact.renamed": EventProjection("contact.renamed", "contact_id"),
    "crm.contact.points.changed": EventProjection("contact.points.changed", "contact_id"),
    "crm.lead.created": EventProjection("lead.created", "lead_id"),
    "crm.lead.stage.changed": EventProjection("lead.stage.changed", "lead_id", "stage"),
    "crm.lead.temperature.changed": EventProjection("lead.temperature.changed", "lead_id", "temperature"),
    "whatsapp.turn.handoff": EventProjection("conversation.handoff.requested", "turn_id"),
    "ingest.handoff.created": EventProjection("conversation.handoff.requested", "lead_id"),
    "privacy.case.state.changed": EventProjection("privacy.case.state.changed", "case_id", "state"),
}

TRANSITIONS = {
    "stage": ("nuevo", "contactado", "en_proceso", "ganado", "perdido"),
    "temperature": ("cold", "warm", "hot"),
    "state": ("pendiente", "en_proceso", "completada"),
}
