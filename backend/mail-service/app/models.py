from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class EmailSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sender_key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    to: list[EmailStr] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=240)
    html: str | None = Field(default=None, max_length=200_000)
    text: str | None = Field(default=None, max_length=200_000)
    reply_to: EmailStr | None = None
    idempotency_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("subject")
    @classmethod
    def reject_header_injection(cls, value: str):
        if "\r" in value or "\n" in value:
            raise ValueError("El asunto contiene caracteres no permitidos.")
        return value

    @model_validator(mode="after")
    def require_content(self):
        if not self.html and not self.text:
            raise ValueError("Debe proporcionarse html o text.")
        return self


class EmailSendResponse(BaseModel):
    success: bool
    status: str
    message_id: str | None
    recipients: int
    provider: str


class LegacyMailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    sender_key: str = Field(alias="senderKey", min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    to: list[EmailStr] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=240)
    html: str | None = Field(default=None, alias="attachedHtml", max_length=200_000)
    text: str | None = Field(default=None, max_length=200_000)
    reply_to: EmailStr | None = Field(default=None, alias="replyTo")
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")

    @field_validator("to", mode="before")
    @classmethod
    def normalize_recipient(cls, value):
        return [value] if isinstance(value, str) else value

    @field_validator("reply_to", mode="before")
    @classmethod
    def normalize_reply_to(cls, value):
        return None if value == "" else value

    @field_validator("subject")
    @classmethod
    def reject_header_injection(cls, value: str):
        if "\r" in value or "\n" in value:
            raise ValueError("El asunto contiene caracteres no permitidos.")
        return value

    @model_validator(mode="after")
    def require_content(self):
        if not self.html and not self.text:
            raise ValueError("Debe proporcionarse attachedHtml o text.")
        return self


class ErrorDetail(BaseModel):
    code: str
    message: str
