from pydantic import BaseModel


class RuleCreate(BaseModel):
    name: str
    rule_type: str = "general"
    content: str
    priority: int = 100
    is_active: bool = True


class RulePatch(BaseModel):
    name: str | None = None
    content: str | None = None
    priority: int | None = None
    is_active: bool | None = None


class RuleRead(BaseModel):
    id: int
    tenant_id: str
    name: str
    rule_type: str
    content: str
    priority: int
    is_active: bool

    model_config = {"from_attributes": True}
