import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.context import BusinessContextDocument, DocumentChunk


@dataclass(frozen=True)
class RetrievedSource:
    document_id: int
    chunk_id: int
    title: str
    score: float
    content: str


TOKEN_RE = re.compile(r"[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]{3,}")


def _tokens(value: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(value)}


def retrieve_sources(db: Session, tenant_id: str, query: str, limit: int = 3) -> list[RetrievedSource]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    rows = db.execute(
        select(DocumentChunk, BusinessContextDocument)
        .join(BusinessContextDocument, BusinessContextDocument.id == DocumentChunk.document_id)
        .where(DocumentChunk.tenant_id == tenant_id, BusinessContextDocument.status == "active")
    ).all()
    ranked: list[RetrievedSource] = []
    for chunk, document in rows:
        content_tokens = _tokens(chunk.content)
        if not content_tokens:
            continue
        overlap = len(query_tokens.intersection(content_tokens))
        score = overlap / max(len(query_tokens), 1)
        if score > 0:
            ranked.append(RetrievedSource(document.id, chunk.id, document.title, min(score, 1.0), chunk.content))
    return sorted(ranked, key=lambda source: source.score, reverse=True)[:limit]
