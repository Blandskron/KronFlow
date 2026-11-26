from typing import Any

from app.api.v1.schemas.agent import AgentActionPayload


TYPED_PROPOSAL_ACTIONS = frozenset(
    {
        "crm.contact.rename",
        "crm.lead.update_stage",
        "crm.opportunity.add_note",
        "crm.conversation.request_handoff",
    }
)
ALLOWED_ACTIONS = {"handoff_human", "none", *TYPED_PROPOSAL_ACTIONS}
VALID_LEAD_STAGES = frozenset({"nuevo", "contactado", "en_proceso", "ganado", "perdido"})


def _valid_typed_payload(action_type: str, payload: dict[str, Any]) -> bool:
    if action_type == "crm.contact.rename":
        name = payload.get("name")
        return isinstance(name, str) and bool(name.strip()) and len(name.strip()) <= 160
    if action_type == "crm.lead.update_stage":
        stage = payload.get("stage")
        return isinstance(stage, str) and stage.strip() in VALID_LEAD_STAGES
    if action_type == "crm.opportunity.add_note":
        note = payload.get("note")
        return isinstance(note, str) and bool(note.strip()) and len(note.strip()) <= 2000
    if action_type == "crm.conversation.request_handoff":
        reason = payload.get("reason")
        return isinstance(reason, str) and bool(reason.strip()) and len(reason.strip()) <= 180
    return True


def prepare_action(action_type: str, payload: dict[str, Any]) -> AgentActionPayload:
    if action_type not in ALLOWED_ACTIONS:
        return AgentActionPayload(type="none", payload={"reason": "action_not_enabled"})
    if action_type in TYPED_PROPOSAL_ACTIONS and not _valid_typed_payload(action_type, payload):
        return AgentActionPayload(type="none", payload={"reason": "invalid_action_payload"})
    return AgentActionPayload(type=action_type, payload=payload)
