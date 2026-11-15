from datetime import datetime

from pydantic import BaseModel, Field


class AgentConfigureRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=160)
    prompt_config: dict = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    role: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, max_length=32)
    prompt_config: dict | None = None


class AgentOut(BaseModel):
    id: int
    name: str
    role: str
    status: str
    prompt_config: dict
    created_at: datetime
    updated_at: datetime

