from app.api.v1.schemas.agent import AgentActionPayload


ALLOWED_ACTIONS = {"handoff_human", "none"}


def prepare_action(action_type: str, payload: dict) -> AgentActionPayload:
    if action_type not in ALLOWED_ACTIONS:
        return AgentActionPayload(type="none", payload={"reason": "action_not_enabled"})
    return AgentActionPayload(type=action_type, payload=payload)
