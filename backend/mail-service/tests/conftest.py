import logging

import httpx
import pytest
import pytest_asyncio

from app.config import ClientConfig, SenderConfig, Settings
from app.email import EmailResult
from app.idempotency import MemoryIdempotencyStore
from app.main import app
from app.rate_limit import RateLimiter
from app.service import EmailService
from app.webhooks import MemoryWebhookEventStore


class FakeProvider:
    def __init__(self):
        self.calls = 0

    async def send(self, message):
        self.calls += 1
        return EmailResult(True, "resend", f"msg-{self.calls}", "accepted")


@pytest_asyncio.fixture
async def client():
    settings = Settings(
        resend_api_key="test-key",
        email_senders_json={"blandskron": SenderConfig.model_validate({"from": "Blandskron <no-reply@example.com>", "reply_to": "reply@example.com"})},
        internal_clients_json={"flowkron": ClientConfig(api_key="internal-test-key", allowed_senders=["blandskron"])},
        rate_limit_requests=100,
        rate_limit_window_seconds=60,
        enable_legacy_mail_endpoint=False,
    )
    provider = FakeProvider()
    store = MemoryIdempotencyStore()
    app.state.settings = settings
    app.state.rate_limiter = RateLimiter(100, 60)
    app.state.audit_logger = logging.getLogger("test")
    app.state.webhook_store = MemoryWebhookEventStore()
    app.state.email_service = EmailService(settings, provider, store)
    app.state.fake_provider = provider
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
