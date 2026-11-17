import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import Settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal, require_internal_token
from app.core.tenant_resolver import resolve_tenant_from_ingest_headers
from app.core import admission
from app.main import app
from app.schemas.ingest import ConsentIn
from app.schemas.lead import LeadListResponse
from app.schemas.tenant import TenantProvisionRequest
from app.services.ingest_service import save_consent
from app.services.tenant_data import lead_to_dict
from app.services.tenant_provisioning_service import provision_tenant
from app.tenant_models.operations import Cliente, Lead


def request(path="/api/v1/leads", method="GET"):
    return Request({"type": "http", "method": method, "path": path, "headers": [], "client": ("127.0.0.1", 1234)})


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.settings = Settings(_env_file=None, jwt_public_key=cls.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())

    def bearer(self, **changes):
        claims = {"user_id": "1", "tenant_id": "1", "jti": "test", "iat": int(time.time()), "exp": int(time.time()) + 60, "iss": self.settings.jwt_issuer, "aud": self.settings.jwt_audience, "token_type": "access", "permissions": ["crm.manage"]}
        claims.update(changes)
        return "Bearer " + jwt.encode(claims, self.key, algorithm="RS256")

    def test_access_works_and_refresh_expired_wrong_audience_and_missing_claims_fail(self):
        self.assertEqual(get_current_principal(request(), self.bearer(), self.settings).tenant_id, 1)
        for change in ({"token_type": "refresh"}, {"token_type": None}, {"exp": 1}, {"aud": "other"}, {"tenant_id": "invalid"}):
            with self.subTest(change=change), self.assertRaises(HTTPException):
                get_current_principal(request(), self.bearer(**change), self.settings)

    def test_empty_internal_token_never_authenticates(self):
        for supplied in (None, "", "change-me-local-internal-token"):
            with self.assertRaises(HTTPException):
                require_internal_token(supplied, Settings(_env_file=None, internal_token=""))
        require_internal_token("synthetic-only", Settings(_env_file=None, internal_token="synthetic-only"))

    def test_viewer_cannot_write_crm_or_agents_but_may_read_crm(self):
        runtime = SimpleNamespace(auth_tenant_id=1, tenant_slug="test", schema_name="tenant_test", tenant_code="test", plan="free", status="active")
        db = MagicMock()
        db.scalar.return_value = runtime
        viewer = CurrentPrincipal("1", 1, "1", ["VIEWER"], ["users.read"], {}, {})
        app.dependency_overrides.update({get_db: lambda: db, get_current_principal: lambda: viewer})
        self.addCleanup(app.dependency_overrides.clear)
        client = TestClient(app)
        with patch("app.api.v1.leads.list_leads", return_value=([], 0)), patch("app.api.v1.leads.update_lead", return_value=None) as write:
            self.assertEqual(client.get("/api/v1/leads").status_code, 200)
            self.assertEqual(client.patch("/api/v1/leads/1", json={}).status_code, 403)
            self.assertEqual(client.get("/api/v1/agents").status_code, 403)
            self.assertEqual(client.get("/api/v1/operational/solicitudes-derechos").status_code, 403)
            write.assert_not_called()
            manager = CurrentPrincipal("1", 1, "1", ["MANAGER"], ["crm.manage"], {}, {})
            app.dependency_overrides[get_current_principal] = lambda: manager
            self.assertEqual(client.patch("/api/v1/leads/1", json={}).status_code, 404)
            write.assert_called_once()

    def test_admission_rejects_invalid_attempts_before_database_or_pbkdf2(self):
        admission._origins.clear()
        admission._global.clear()

        db = MagicMock()
        db.scalar.return_value = SimpleNamespace(ingest_key_hash="unused")
        with patch("app.core.tenant_resolver.verify_secret", return_value=False) as verify:
            for _ in range(600):
                with self.assertRaises(HTTPException):
                    resolve_tenant_from_ingest_headers(request(), "known", "invalid", None, None, db)
            calls = verify.call_count
            with self.assertRaises(HTTPException) as error:
                resolve_tenant_from_ingest_headers(request(), "known", "invalid", None, None, db)
            self.assertEqual(error.exception.status_code, 429)
            self.assertEqual(verify.call_count, calls)
            self.assertEqual(db.scalar.call_count, calls)
        admission._origins.clear()
        admission._global.clear()

    def test_oversized_chunked_ingest_is_rejected_before_database(self):
        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        self.addCleanup(app.dependency_overrides.clear)
        over = b"x" * 550_000
        result = TestClient(app).post("/api/v1/ingest/whatsapp/message", content=iter([over, over]), headers={"Content-Type": "application/json", "X-Correlation-ID": "controlled"})
        self.assertEqual(result.status_code, 413)
        self.assertEqual(result.headers["X-Correlation-ID"], "controlled")
        db.scalar.assert_not_called()

    def test_consent_preserves_existing_name_and_withdraws(self):
        client = SimpleNamespace(nombre="Existing customer", fecha_consentimiento=None)
        db = MagicMock()
        db.scalar.return_value = client
        with patch("app.services.ingest_service.bind_tenant_session"), patch("app.services.ingest_service.get_consent", return_value={}):
            for accepted in (True, False, True):
                save_consent(db, SimpleNamespace(schema_name="tenant_test"), ConsentIn(phone="12025550138", accepted=accepted, policy_version="test"))
                self.assertEqual(client.nombre, "Existing customer")
                self.assertEqual(client.consentimiento_datos, accepted)

    def test_reprovision_does_not_resume_suspended_runtime(self):
        runtime = SimpleNamespace(auth_tenant_id=1, schema_name="tenant_test", status="suspended")
        db = MagicMock()
        db.scalar.return_value = runtime
        with patch("app.services.tenant_provisioning_service.apply_tenant_schema") as apply_schema:
            provision_tenant(db, TenantProvisionRequest(auth_tenant_id=1, tenant_slug="test", tenant_name="Test", plan="free"))
        apply_schema.assert_not_called()
        self.assertEqual(runtime.status, "suspended")

    def test_whatsapp_lead_without_email_keeps_the_list_available(self):
        now = datetime.now(timezone.utc)
        contact = Cliente(id=1, rut="synthetic", nombre="Contacto", email=None, telefono="12025550138",
                          canal_origen="whatsapp", whatsapp_id="12025550138")
        lead = Lead(id=1, cliente_id=1, cliente=contact, score_lead=0, clasificacion="frio",
                    estado="nuevo", creado_en=now, actualizado_en=now)
        result = LeadListResponse(items=[lead_to_dict(lead)], total=1, limit=50, offset=0)
        self.assertEqual(result.items[0].email, "")
        self.assertEqual(result.items[0].phone, "12025550138")
