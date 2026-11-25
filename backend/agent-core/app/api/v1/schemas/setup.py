from pydantic import BaseModel


class SetupSessionCreate(BaseModel):
    objective: str = "build_business_context"


class SetupMessageCreate(BaseModel):
    content: str


class SetupSessionRead(BaseModel):
    session_id: str
    next_question: str


class GeneratedContextRead(BaseModel):
    summary: str
    status: str = "draft"
