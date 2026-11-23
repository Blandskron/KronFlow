from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    sender: str
    recipients: list[str]
    subject: str
    html: str | None
    text: str | None
    reply_to: str | None
    idempotency_key: str


@dataclass(frozen=True)
class EmailResult:
    success: bool
    provider: str
    message_id: str | None
    status: str
    error_code: str | None = None


class EmailProvider(Protocol):
    async def send(self, message: EmailMessage) -> EmailResult:
        ...
