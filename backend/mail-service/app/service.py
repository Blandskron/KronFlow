import asyncio
import time

from .config import ConfigurationError, Settings
from .email import EmailMessage, EmailResult
from .idempotency import IdempotencyStore
from .models import EmailSendRequest
from .resend_provider import ProviderError, ResendEmailProvider
from .senders import resolve_sender


class EmailService:
    def __init__(self, settings: Settings, provider: ResendEmailProvider, idempotency: IdempotencyStore):
        self.settings = settings
        self.provider = provider
        self.idempotency = idempotency

    async def send(self, client_id: str, request: EmailSendRequest) -> tuple[EmailResult, bool]:
        sender = resolve_sender(self.settings, request.sender_key)
        if request.reply_to and sender.reply_to and str(request.reply_to).lower() != sender.reply_to.lower():
            raise ConfigurationError("reply_to no autorizado para el sender_key.")
        reservation = await self.idempotency.reserve(client_id, request.idempotency_key)
        if not reservation:
            for _ in range(10):
                cached = await self.idempotency.get(client_id, request.idempotency_key)
                if cached:
                    return cached, True
                await asyncio.sleep(0.05)
            raise ProviderError("IDEMPOTENCY_IN_PROGRESS")
        message = EmailMessage(
            sender=sender.from_address,
            recipients=[str(item) for item in request.to],
            subject=request.subject,
            html=request.html,
            text=request.text,
            reply_to=sender.reply_to,
            idempotency_key=f"{client_id}:{request.idempotency_key}",
        )
        started = time.perf_counter()
        try:
            result = await self.provider.send(message)
        except Exception:
            raise
        finally:
            _ = time.perf_counter() - started
        await self.idempotency.complete(client_id, request.idempotency_key, result)
        return result, False
