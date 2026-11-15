import asyncio
import logging
import random

import httpx

from .config import Settings
from .email import EmailMessage, EmailProvider, EmailResult

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False, provider_status: int | None = None):
        self.code = code
        self.retryable = retryable
        self.provider_status = provider_status
        super().__init__(code)


class ResendEmailProvider(EmailProvider):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client
        self._owns_client = client is None

    async def send(self, message: EmailMessage) -> EmailResult:
        if not self.settings.resend_api_key:
            raise ProviderError("PROVIDER_NOT_CONFIGURED")
        payload = {
            "from": message.sender,
            "to": message.recipients,
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        if message.reply_to:
            payload["reply_to"] = message.reply_to
        payload = {key: value for key, value in payload.items() if value is not None}
        headers = {
            "Authorization": f"Bearer {self.settings.resend_api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": message.idempotency_key,
        }
        attempts = 3
        client = self.client or httpx.AsyncClient(
            base_url=self.settings.resend_base_url.rstrip("/"),
            timeout=self.settings.resend_timeout_seconds,
        )
        try:
            for attempt in range(attempts):
                try:
                    response = await client.post("/emails", headers=headers, json=payload)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == attempts - 1:
                        raise ProviderError("PROVIDER_UNAVAILABLE", retryable=True) from exc
                    await asyncio.sleep((2**attempt) * 0.2 + random.uniform(0, 0.1))
                    continue
                if response.is_success:
                    data = response.json()
                    return EmailResult(True, "resend", data.get("id"), "accepted")
                retryable = response.status_code == 429 or response.status_code in {500, 502, 503, 504}
                if retryable and attempt < attempts - 1:
                    await asyncio.sleep((2**attempt) * 0.2 + random.uniform(0, 0.1))
                    continue
                if response.status_code in {400, 401, 403, 422}:
                    raise ProviderError("PROVIDER_REQUEST_REJECTED", provider_status=response.status_code)
                raise ProviderError("PROVIDER_UNAVAILABLE", retryable=True, provider_status=response.status_code)
            raise ProviderError("PROVIDER_UNAVAILABLE", retryable=True)
        finally:
            if self._owns_client:
                await client.aclose()
