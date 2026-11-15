from pathlib import Path
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

Path("flowkron_agent_core.db").unlink(missing_ok=True)
os.environ["PERSISTENCE_MODE"] = "local"
os.environ["ALLOW_LOCAL_DB_BOOTSTRAP"] = "true"
os.environ["ALLOW_INSECURE_TENANT_HEADER"] = "true"
os.environ["AZURE_OPENAI_ENABLED"] = "false"

from app.core.database import create_tables
from app.infrastructure.operational_context import OperationalContextClient
from app.main import app
from app.services import template_catalog
from app.services.template_catalog import _render_docx


create_tables()
client = TestClient(app)
HEADERS_A = {"X-Tenant-Id": "tenant-a"}
HEADERS_B = {"X-Tenant-Id": "tenant-b"}


def unwrap(response):
    payload = response.json()
    return payload["data"] if payload.get("success") is True else payload


def test_healthcheck():
    response = client.get("/health")
    assert response.status_code == 200
    assert unwrap(response)["status"] == "ok"


def test_forms_and_submission():
    forms = client.get("/api/v1/context/forms", headers=HEADERS_A)
    assert forms.status_code == 200
    form_id = unwrap(forms)[0]["id"]
    submission = client.post(f"/api/v1/context/forms/{form_id}/submit", headers=HEADERS_A, json={"payload": {"company_name": "Flowkron"}})
    assert submission.status_code == 201
    assert unwrap(submission)["tenant_id"] == "tenant-a"


def test_context_templates_can_be_downloaded_as_word_and_pdf():
    response = client.get("/api/v1/context/templates", headers=HEADERS_A)
    assert response.status_code == 200
    templates = unwrap(response)
    assert len(templates) == 5
    assert all({option["format"] for option in template["download_options"]} == {"docx", "pdf"} for template in templates)

    docx_option = next(option for option in templates[0]["download_options"] if option["format"] == "docx")
    docx = client.get(f"/api/v1/context/templates/{docx_option['template_id']}/download", headers=HEADERS_A)
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument")
    assert docx.content.startswith(b"PK")

    pdf_option = next(option for option in templates[0]["download_options"] if option["format"] == "pdf")
    pdf = client.get(f"/api/v1/context/templates/{pdf_option['template_id']}/download", headers=HEADERS_A)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")


def test_context_templates_fall_back_to_packaged_catalog(monkeypatch):
    monkeypatch.delenv(template_catalog.CONTEXT_TEMPLATE_ROOT_ENV, raising=False)
    monkeypatch.setattr(template_catalog, "MONOREPO_TEMPLATE_ROOT", Path("missing-template-root"))

    assert template_catalog.resolve_template_root() == template_catalog.PACKAGED_TEMPLATE_ROOT
    templates = template_catalog.list_context_template_groups()

    assert len(templates) == 5
    assert all({option.format for option in template.download_options} == {"docx", "pdf"} for template in templates)


def test_context_status_reports_real_documents_only():
    empty = client.get("/api/v1/context/status", headers=HEADERS_B)
    assert empty.status_code == 200
    empty_status = unwrap(empty)
    assert empty_status["progress_percent"] == 0
    assert empty_status["agent_status"] == "not_configured"
    assert empty_status["active_documents_count"] == 0
    assert empty_status["documents"] == []

    doc = client.post(
        "/api/v1/context/documents/upload",
        headers=HEADERS_B,
        json={"title": "Politicas", "filename": "politicas.md", "content": "Aceptamos pagos con transferencia bancaria.", "status": "active"},
    )
    assert doc.status_code == 201

    status_response = client.get("/api/v1/context/status", headers=HEADERS_B)
    assert status_response.status_code == 200
    status_payload = unwrap(status_response)
    assert status_payload["progress_percent"] == 20
    assert status_payload["agent_status"] == "pending"
    assert status_payload["active_documents_count"] == 1
    assert status_payload["last_updated_at"]
    assert status_payload["documents"][0]["filename"] == "politicas.md"


def test_document_upload_and_contextual_response():
    doc = client.post(
        "/api/v1/context/documents/upload",
        headers=HEADERS_A,
        json={"title": "Horarios", "filename": "horarios.md", "content": "La empresa atiende de lunes a viernes de 9 a 18 horas.", "status": "active"},
    )
    assert doc.status_code == 201
    payload = {
        "tenant_id": "tenant-a",
        "channel": "webchat",
        "conversation_id": "conv-1",
        "customer": {"external_id": "cust-1"},
        "message": {"type": "text", "content": "Atienden lunes viernes 18 horas?", "attachments": []},
        "metadata": {"raw_payload": {}},
    }
    response = client.post("/api/v1/agent/messages", headers=HEADERS_A, json=payload)
    assert response.status_code == 200
    body = unwrap(response)
    assert body["confidence"] > 0
    assert body["sources"]


def test_docx_upload_file_is_extracted_and_used_as_context():
    docx_content = _render_docx("# Contexto\n\nLa empresa vende drones industriales para inspeccion minera.")
    doc = client.post(
        "/api/v1/context/documents/upload-file",
        headers=HEADERS_A,
        data={"title": "Catalogo drones", "status": "active", "priority": "100"},
        files={"file": ("drones.docx", docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert doc.status_code == 201
    assert unwrap(doc)["filename"] == "drones.docx"

    payload = {
        "tenant_id": "tenant-a",
        "channel": "webchat",
        "conversation_id": "conv-docx",
        "customer": {"external_id": "cust-docx"},
        "message": {"type": "text", "content": "Venden drones industriales?", "attachments": []},
        "metadata": {"raw_payload": {}},
    }
    response = client.post("/api/v1/agent/messages", headers=HEADERS_A, json=payload)
    assert response.status_code == 200
    body = unwrap(response)
    assert body["confidence"] > 0
    assert body["sources"]


def test_universal_message_without_context_requires_human():
    payload = {
        "tenant_id": "tenant-b",
        "channel": "whatsapp",
        "conversation_id": "conv-empty",
        "customer": {"external_id": "cust-2"},
        "message": {"type": "text", "content": "Tienen garantias extendidas?", "attachments": []},
        "metadata": {"raw_payload": {}},
    }
    response = client.post("/api/v1/agent/messages", headers=HEADERS_B, json=payload)
    assert response.status_code == 200
    assert unwrap(response)["requires_human"] is True


def test_tenant_validation_and_cross_tenant_protection():
    payload = {
        "tenant_id": "tenant-b",
        "channel": "email",
        "conversation_id": "bad-tenant",
        "customer": {"external_id": "cust-3"},
        "message": {"type": "text", "content": "Hola", "attachments": []},
        "metadata": {"raw_payload": {}},
    }
    response = client.post("/api/v1/agent/messages", headers=HEADERS_A, json=payload)
    assert response.status_code == 403

    docs = client.get("/api/v1/context/documents", headers=HEADERS_B)
    assert docs.status_code == 200
    assert all(document["tenant_id"] == "tenant-b" for document in unwrap(docs))


def test_operational_context_client_unwraps_standard_success_envelope(monkeypatch):
    document_payload = {
        "id": 1,
        "tenant_id": "2",
        "title": "01-perfil-de-empresa-blandskron",
        "filename": "template-12 (2).pdf",
        "content_type": "application/pdf",
        "status": "active",
        "priority": 100,
        "version": 1,
        "source_type": "upload",
        "created_at": "2026-07-09T19:03:30.316636Z",
        "updated_at": "2026-07-09T19:03:30.316636Z",
        "error_message": None,
    }

    class FakeResponse:
        status_code = 201

        def json(self):
            return {
                "success": True,
                "status": {"code": 201, "message": "Request completed successfully"},
                "data": document_payload,
                "meta": {"service": "operational-service"},
            }

    class FakeHttpClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def request(self, method, url, headers, **kwargs):
            assert headers["X-Internal-Token"] == "test-token"
            return FakeResponse()

    monkeypatch.setattr(
        "app.infrastructure.operational_context.get_settings",
        lambda: SimpleNamespace(operational_service_url="http://operational", internal_token="test-token"),
    )
    monkeypatch.setattr("app.infrastructure.operational_context.httpx.Client", FakeHttpClient)

    assert OperationalContextClient()._request("POST", "/internal/tenants/2/context/documents") == document_payload
