import pytest
from app.main import app


AUTH = {"Authorization": "Bearer internal-test-key"}


@pytest.mark.asyncio
async def test_health_and_ready(client):
    assert (await client.get("/health")).json() == {"status": "ok"}
    ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["provider"] == "resend"


@pytest.mark.asyncio
async def test_requires_bearer(client):
    response = await client.post("/api/v1/emails/send", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unknown_client_and_sender_are_rejected(client):
    unknown = await client.post("/api/v1/emails/send", headers={"Authorization": "Bearer wrong"}, json={})
    assert unknown.status_code == 401
    forbidden = await client.post("/api/v1/emails/send", headers=AUTH, json={
        "sender_key": "unknown",
        "to": ["person@example.com"],
        "subject": "Test",
        "text": "Body",
        "idempotency_key": "unknown-123",
    })
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_valid_send_and_response(client):
    response = await client.post("/api/v1/emails/send", headers=AUTH, json={
        "sender_key": "blandskron",
        "to": ["person@example.com"],
        "subject": "Test",
        "html": "<p>Body</p>",
        "text": "Body",
        "idempotency_key": "example1",
    })
    assert response.status_code == 200
    assert response.json() == {"success": True, "status": "accepted", "message_id": "msg-1", "recipients": 1, "provider": "resend"}


@pytest.mark.asyncio
async def test_idempotency_returns_stored_result(client):
    payload = {
        "sender_key": "blandskron",
        "to": ["person@example.com"],
        "subject": "Same",
        "text": "Body",
        "idempotency_key": "example2",
    }
    first = await client.post("/api/v1/emails/send", headers=AUTH, json=payload)
    second = await client.post("/api/v1/emails/send", headers=AUTH, json=payload)
    assert first.json()["message_id"] == second.json()["message_id"]
    assert app.state.fake_provider.calls == 1


@pytest.mark.asyncio
async def test_strict_payload_and_content_validation(client):
    extra = await client.post("/api/v1/emails/send", headers=AUTH, json={
        "sender_key": "blandskron", "to": ["person@example.com"], "subject": "Test",
        "text": "Body", "idempotency_key": "example3", "from": "bad@example.com",
    })
    assert extra.status_code == 422
    missing_content = await client.post("/api/v1/emails/send", headers=AUTH, json={
        "sender_key": "blandskron", "to": ["person@example.com"], "subject": "Test",
        "idempotency_key": "example4",
    })
    assert missing_content.status_code == 422


@pytest.mark.asyncio
async def test_legacy_endpoint_is_disabled_by_default(client):
    response = await client.post("/mail", headers=AUTH, json={
        "senderKey": "blandskron", "to": ["person@example.com"], "subject": "Test",
        "text": "Body", "idempotencyKey": "legacy-123",
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_endpoint_accepts_only_safe_transitional_shape(client):
    app.state.settings.enable_legacy_mail_endpoint = True
    response = await client.post("/mail", headers=AUTH, json={
        "senderKey": "blandskron", "to": "person@example.com", "subject": "Legacy",
        "text": "Body", "replyTo": "", "idempotencyKey": "legacy-456",
    })
    assert response.status_code == 200
    app.state.settings.enable_legacy_mail_endpoint = False
