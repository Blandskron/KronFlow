from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator

from app.services.contact_points import normalize_email, normalize_phone


class ContactOut(BaseModel):
    id: int
    full_name: str
    email: str | None
    phone: str | None
    source: str
    created_at: datetime


class ContactDetailOut(ContactOut):
    normalized_email: str | None = None
    normalized_phone: str | None = None


class ContactListResponse(BaseModel):
    items: list[ContactOut]
    total: int
    limit: int
    offset: int


class ContactNameUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=180)
    expected_full_name: str

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Contact name must not be blank")
        return value.strip()


class ContactPointsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(max_length=254)
    phone: str | None = Field(max_length=80)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_email(value)
        if normalized is None:
            raise ValueError("Enter a supported email address")
        return normalized

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_phone(value)
        if normalized is None:
            raise ValueError("Enter a phone number with an explicit international prefix")
        return normalized


class ContactCreateIn(ContactPointsIn):
    request_id: UUID4
    full_name: str = Field(min_length=1, max_length=180)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=80)

    @field_validator("full_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ContactCreateOut(BaseModel):
    contact: ContactDetailOut
    created: bool


class ContactPointsUpdate(ContactPointsIn):
    expected_email: str | None
    expected_phone: str | None
