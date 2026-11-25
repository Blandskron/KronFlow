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
    "conversation.handoff.requested": EventProjection("conversation.handoff.requested", "conversation_id"),
    "conversation.claimed": EventProjection("conversation.claimed", "conversation_id"),
    "conversation.control.changed": EventProjection("conversation.control.changed", "conversation_id"),
    "opportunity.stage.changed": EventProjection("opportunity.stage.changed", "opportunity_id"),
    "opportunity.won": EventProjection("opportunity.won", "opportunity_id"),
    "opportunity.lost": EventProjection("opportunity.lost", "opportunity_id"),
    "ai.proposal.created": EventProjection("ai.proposal.created", "proposal_id"),
    "ai.proposal.approved": EventProjection("ai.proposal.approved", "proposal_id"),
    "ai.proposal.rejected": EventProjection("ai.proposal.rejected", "proposal_id"),
    "ai.proposal.executed": EventProjection("ai.proposal.executed", "proposal_id"),
    "privacy.case.state.changed": EventProjection("privacy.case.state.changed", "case_id", "state"),
}

TRANSITIONS = {
    "stage": ("nuevo", "contactado", "en_proceso", "ganado", "perdido"),
    "temperature": ("cold", "warm", "hot"),
    "state": ("pendiente", "en_proceso", "completada"),
}
