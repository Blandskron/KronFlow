"""Tests for the idempotent demo-only dataset seeder endpoint."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import app
from app.schemas.tenant import TenantProvisionRequest
from app.services.tenant_provisioning_service import provision_tenant
from test_message_identity import PostgresCase


class DemoSeedTests(PostgresCase):
    def setUp(self) -> None:
        super().setUp()
        self.internal_token = "demo-seed-internal-token"

        def _override_db():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_settings] = lambda: Settings(internal_token=self.internal_token)
        self.addCleanup(app.dependency_overrides.clear)

    def test_demo_seed_populates_all_modules_and_is_idempotent(self) -> None:
        with Session(self.engine) as db:
            runtime, _, _ = provision_tenant(
                db,
                TenantProvisionRequest(auth_tenant_id=401, tenant_slug="demo-seed-co", plan="starter"),
            )
            tenant_id = runtime.auth_tenant_id

        headers = {"X-Internal-Token": self.internal_token}
        client = TestClient(app)

        first = client.post(f"/internal/tenants/{tenant_id}/demo-seed", headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        body = first.json().get("data", first.json())
        self.assertTrue(body["seeded"])
        self.assertFalse(body["already_populated"])
        self.assertEqual(body["counts"]["contacts"], 6)
        self.assertEqual(body["counts"]["leads"], 6)
        self.assertEqual(body["counts"]["conversations"], 4)
        self.assertEqual(body["counts"]["opportunities"], 5)
        self.assertEqual(body["counts"]["ai_proposals"], 2)
        self.assertEqual(body["counts"]["agents"], 2)
        self.assertEqual(body["counts"]["workflows"], 2)
        self.assertEqual(body["counts"]["campaigns"], 1)
        self.assertEqual(body["counts"]["webchat_widgets"], 1)
        self.assertEqual(body["counts"]["privacy_requests"], 1)

        # Calling a second time must be a safe no-op.
        second = client.post(f"/internal/tenants/{tenant_id}/demo-seed", headers=headers)
        self.assertEqual(second.status_code, 200, second.text)
        body2 = second.json().get("data", second.json())
        self.assertFalse(body2["seeded"])
        self.assertTrue(body2["already_populated"])


if __name__ == "__main__":
    unittest.main()
