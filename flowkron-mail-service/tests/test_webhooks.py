import base64
import hashlib
import hmac
import json
import time

import pytest
from app.main import app


@pytest.mark.asyncio
async def test_invalid_webhook_signature(client):
    response = await client.post("/api/v1/webhooks/resend", content=b"{}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_webhook_signature(client):
    secret = base64.b64encode(b"webhook-secret").decode()
    app.state.settings.resend_webhook_secret = f"whsec_{secret}"
    body = json.dumps({"type": "email.delivered"}).encode()
    event_id = "evt-1"
    timestamp = str(int(time.time()))
    signature = base64.b64encode(hmac.new(b"webhook-secret", f"{event_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()).decode()
    response = await client.post("/api/v1/webhooks/resend", content=body, headers={"svix-id": event_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"})
    assert response.status_code == 200
    assert response.json()["success"] is True
