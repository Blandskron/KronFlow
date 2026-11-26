from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.contracts import active_correlation
from app.infrastructure.document_processing.chunker import chunk_text


@dataclass(frozen=True)
class OperationalContextSource:
    document_id: int
    chunk_id: int
    title: str
    score: float
    content: str


class OperationalContextClient:
    def create_document(
        self,
        *,
        tenant_id: str,
        title: str,
        filename: str,
        content: str,
        content_type: str,
        status_value: str,
        priority: int,
    ) -> dict[str, Any]:
        chunks = [
            {
                "chunk_index": index,
                "content": chunk,
                "token_count": len(chunk.split()),
                "source_ref": f"{filename}#{index}",
            }
            for index, chunk in enumerate(chunk_text(content))
        ]
        return self._request(
            "POST",
            f"/internal/tenants/{tenant_id}/context/documents",
            json={
                "tenant_id": tenant_id,
                "title": title,
                "filename": filename,
                "content_type": content_type,
                "status": status_value,
                "priority": priority,
                "raw_text": content,
                "chunks": chunks,
            },
        )

    def list_documents(self, tenant_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/internal/tenants/{tenant_id}/context/documents")

    def get_document(self, tenant_id: str, document_id: int) -> dict[str, Any]:
        return self._request("GET", f"/internal/tenants/{tenant_id}/context/documents/{document_id}")

    def patch_document(self, tenant_id: str, document_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/internal/tenants/{tenant_id}/context/documents/{document_id}", json=payload)

    def delete_document(self, tenant_id: str, document_id: int) -> None:
        self._request("DELETE", f"/internal/tenants/{tenant_id}/context/documents/{document_id}")

    def get_status(self, tenant_id: str) -> dict[str, Any]:
        return self._request("GET", f"/internal/tenants/{tenant_id}/context/status")

    def retrieve_sources(
        self,
        tenant_id: str,
        query: str,
        limit: int = 3,
        *,
        document_ids: Sequence[int] | None = None,
    ) -> list[OperationalContextSource]:
        body: dict[str, Any] = {"query": query, "limit": limit}
        if document_ids:
            body["document_ids"] = [int(doc_id) for doc_id in document_ids]
        payload = self._request(
            "POST",
            f"/internal/tenants/{tenant_id}/context/retrieve",
            json=body,
        )
        sources = []
        for item in payload:
            score = float(item["score"])
            content = item["content"]
            if not 0.0 <= score <= 1.0 or not isinstance(content, str) or not content.strip():
                raise ValueError("Invalid Operational context source")
            sources.append(OperationalContextSource(
                document_id=int(item["document_id"]),
                chunk_id=int(item["chunk_id"]),
                title=str(item["title"]),
                score=score,
                content=content,
            ))
        return sources

    def list_rules(self, tenant_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/internal/tenants/{tenant_id}/context/rules")

    def create_rule(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/internal/tenants/{tenant_id}/context/rules", json=payload)

    def patch_rule(self, tenant_id: str, rule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/internal/tenants/{tenant_id}/context/rules/{rule_id}", json=payload)

    def delete_rule(self, tenant_id: str, rule_id: int) -> None:
        self._request("DELETE", f"/internal/tenants/{tenant_id}/context/rules/{rule_id}")

    def record_trace(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/internal/tenants/{tenant_id}/context/traces", json=payload)

    def get_trace(self, tenant_id: str, trace_id: int) -> dict[str, Any]:
        return self._request("GET", f"/internal/tenants/{tenant_id}/context/traces/{trace_id}")

    def list_conversation_traces(self, tenant_id: str, conversation_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/internal/tenants/{tenant_id}/context/conversations/{conversation_id}/traces")

    def create_setup_session(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/internal/tenants/{tenant_id}/context/setup-sessions", json=payload)

    def send_setup_message(self, tenant_id: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/internal/tenants/{tenant_id}/context/setup-sessions/{session_id}/messages", json=payload)

    def generate_setup_context(self, tenant_id: str, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/internal/tenants/{tenant_id}/context/setup-sessions/{session_id}/generate-context")

    def resolve_active_agent(
        self,
        tenant_id: str,
        *,
        agent_id: int | None = None,
        agent_revision_id: int | None = None,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if agent_revision_id is not None:
            params["agent_revision_id"] = agent_revision_id
        return self._request("GET", f"/internal/tenants/{tenant_id}/context/agents/resolve", params=params or None)

    def list_conversation_memory(self, tenant_id: str, conversation_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/internal/tenants/{tenant_id}/context/conversations/{conversation_id}/memory",
            params={"limit": limit},
        )

    def create_proposal(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/internal/tenants/{tenant_id}/context/proposals", json=payload)

    def record_ai_usage(
        self,
        tenant_id: str,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        estimated_cost_usd: Decimal,
        is_simulation: bool = False,
        agent_id: int | None = None,
        agent_revision_id: int | None = None,
        pricing_version: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/internal/tenants/{tenant_id}/context/ai-usage",
            json={
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": latency_ms,
                "estimated_cost_usd": str(estimated_cost_usd),
                "is_simulation": is_simulation,
                "agent_id": agent_id,
                "agent_revision_id": agent_revision_id,
                "pricing_version": pricing_version,
            },
        )

    def require_active_workspace(self, tenant_id: str) -> None:
        runtime = self._request("GET", f"/internal/tenants/{int(tenant_id)}/runtime")
        if runtime.get("status") != "active":
            raise HTTPException(status_code=403, detail="Workspace is not active")

    def _request(self, method: str, path: str, **kwargs):
        settings = get_settings()
        url = f"{settings.operational_service_url.rstrip('/')}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Internal-Token"] = settings.internal_token
        if (correlation := active_correlation.get()) is not None:
            headers["X-Correlation-ID"] = correlation
        try:
            with httpx.Client(timeout=15) as client:
                response = client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Operational context service is unavailable",
            ) from exc
        if response.status_code >= 400:
            detail: Any
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text
            raise HTTPException(status_code=response.status_code, detail=detail or "Operational context request failed")
        if response.status_code == status.HTTP_204_NO_CONTENT:
            return None
        return self._unwrap_response_payload(response.json())

    def _unwrap_response_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            return payload["data"]
        return payload


operational_context_client = OperationalContextClient()
