from io import BytesIO
import time
import zipfile

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import Settings
from app.core.security import CurrentPrincipal, get_current_principal
from app.core.tenant import resolve_tenant
from app.infrastructure.document_processing.extractor import DocumentExtractionError, extract_text_from_upload
from app.main import app


def request(path="/api/v1/context/documents/upload"):
    return Request({"type": "http", "method": "POST", "path": path, "headers": []})


def test_refresh_wrong_audience_and_malformed_credentials_rejected():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(_env_file=None, jwt_public_key=key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(), allow_insecure_tenant_header=True)
    claims = {"user_id": "1", "tenant_id": "1", "jti": "test", "iat": int(time.time()), "exp": int(time.time()) + 60, "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "token_type": "access"}
    bearer = lambda c: "Bearer " + jwt.encode(c, key, algorithm="RS256")
    assert get_current_principal(request(), bearer(claims), None, settings).tenant_id == "1"
    for change in ({"token_type": "refresh"}, {"exp": 1}, {"aud": "other"}, {"token_type": None}):
        with pytest.raises(HTTPException):
            get_current_principal(request(), bearer({**claims, **change}), "1", settings)
    with pytest.raises(HTTPException):
        get_current_principal(request(), "Bearer invalid", "1", settings)


def test_viewer_rejected_before_context_write_and_authorized_user_keeps_access(monkeypatch):
    viewer = CurrentPrincipal("1", "1", ["VIEWER"], ["users.read"], {"token_type": "access"})
    monkeypatch.setitem(app.dependency_overrides, get_current_principal, lambda: viewer)
    response = TestClient(app).post("/api/v1/context/documents/upload", json={"title": "Test", "filename": "test.txt", "content": "Should not be stored"})
    assert response.status_code == 403
    editor = CurrentPrincipal("1", "1", ["MANAGER"], ["agents.create"], {"token_type": "access"})
    assert resolve_tenant(request(), editor).tenant_id == "1"


def docx(xml):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_docx_expansion_complexity_and_entities_are_bounded():
    assert "Hello" in extract_text_from_upload("normal.docx", docx('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:t>Hello</w:t></w:p></w:document>'))
    for xml in (b" " * (8 * 1024 * 1024 + 1), b"<a>" * 65 + b"</a>" * 65, b'<!DOCTYPE a [<!ENTITY x "text">]><a>&x;</a>'):
        with pytest.raises(DocumentExtractionError):
            extract_text_from_upload("malformed.docx", docx(xml))


def test_oversized_and_chunked_context_body_rejected_before_parsing():
    client = TestClient(app)
    body = b"x" * (5_242_880 + 65_537)
    for content in (body, iter([body[:3_000_000], body[3_000_000:]])):
        result = client.post("/api/v1/context/documents/upload", content=content, headers={"Content-Type": "application/json"})
        assert result.status_code == 413
        assert result.headers["X-Correlation-ID"]
        assert result.json()["status"] == 413


def test_pdf_accepts_escaped_parentheses_and_rejects_unclosed_literal():
    assert extract_text_from_upload("test.pdf", br"BT (Hello \(world\)) Tj ET") == "Hello (world)"
    with pytest.raises(DocumentExtractionError):
        extract_text_from_upload("test.pdf", b"(" * 100_000)
