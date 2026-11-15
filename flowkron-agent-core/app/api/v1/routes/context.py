from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.schemas.context import (
    BusinessContextStatusRead,
    DocumentCreate,
    DocumentPatch,
    DocumentRead,
    FormRead,
    FormSubmissionCreate,
    FormSubmissionRead,
    TemplateRead,
)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.tenant import TenantContext, resolve_tenant
from app.infrastructure.document_processing.chunker import chunk_text
from app.infrastructure.document_processing.extractor import DocumentExtractionError, extract_text_from_upload
from app.infrastructure.operational_context import operational_context_client
from app.models.context import (
    BusinessContextDocument,
    BusinessContextField,
    BusinessContextForm,
    BusinessContextFormSubmission,
    DocumentChunk,
)
from app.services.template_catalog import get_context_template, list_context_template_groups, render_template_file

router = APIRouter(prefix="/api/v1/context", tags=["Business Context"])


BASE_FORMS = {
    "company-profile": ["company_name", "industry", "short_description", "long_description", "website", "location", "branches", "business_hours", "official_channels", "communication_tone", "what_company_does", "what_company_does_not_do", "customer_types"],
    "products-services": ["name", "category", "description", "price_range", "availability", "conditions", "benefits", "target_audience", "faq", "restrictions", "internal_link_or_code"],
    "faq": ["question", "official_answer", "category", "channel", "priority", "source", "updated_at"],
    "attention-rules": ["auto_reply_when", "handoff_when", "questions_not_allowed", "required_data_before_scheduling", "angry_customer_policy", "price_request_policy", "executive_request_policy", "tone", "words_to_avoid", "business_hours_policy"],
    "commercial-policies": ["exchanges", "returns", "warranties", "payment_methods", "delivery_terms", "reservation_terms", "scheduling_terms", "cancellations", "refunds", "promotions", "legal_or_commercial_restrictions"],
}

RECOMMENDED_CONTEXT_DOCUMENTS = 5


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _document_payload(document) -> dict:
    return {
        "id": document.id,
        "tenant_id": document.tenant_id,
        "title": document.title,
        "filename": document.filename,
        "content_type": getattr(document, "content_type", None),
        "status": document.status,
        "priority": document.priority,
        "version": document.version,
        "source_type": getattr(document, "source_type", "upload"),
        "created_at": _iso(getattr(document, "created_at", None)),
        "updated_at": _iso(getattr(document, "updated_at", None)),
        "error_message": getattr(document, "error_message", None),
    }


def _document_actions() -> dict[str, bool]:
    settings = get_settings()
    local_document_mutations = settings.persistence_mode != "operational"
    return {
        "delete": local_document_mutations,
        "patch": local_document_mutations,
        "replace": False,
        "retry_processing": False,
    }


def _status_from_documents(documents: list[dict]) -> BusinessContextStatusRead:
    active_documents = [document for document in documents if document["status"] == "active"]
    active_count = len(active_documents)
    progress_percent = min(round((active_count / RECOMMENDED_CONTEXT_DOCUMENTS) * 100), 100) if active_count else 0
    timestamps = [
        value
        for document in documents
        for value in (document.get("updated_at"), document.get("created_at"))
        if value
    ]
    if not documents:
        agent_status = "not_configured"
    elif any(document["status"] in {"rejected", "error"} for document in documents):
        agent_status = "error"
    elif active_count >= RECOMMENDED_CONTEXT_DOCUMENTS:
        agent_status = "trained"
    elif active_count > 0:
        agent_status = "pending"
    else:
        agent_status = "processing"
    return BusinessContextStatusRead(
        progress_percent=progress_percent,
        agent_status=agent_status,
        last_updated_at=max(timestamps) if timestamps else None,
        active_documents_count=active_count,
        documents=documents,
        document_actions=_document_actions(),
    )


def persist_context_document(
    *,
    tenant_id: str,
    title: str,
    filename: str,
    content: str,
    content_type: str,
    status_value: str,
    priority: int,
    db: Session,
):
    settings = get_settings()
    if settings.persistence_mode == "operational":
        return operational_context_client.create_document(
            tenant_id=tenant_id,
            title=title,
            filename=filename,
            content=content,
            content_type=content_type,
            status_value=status_value,
            priority=priority,
        )
    require_local_persistence()
    document = BusinessContextDocument(
        tenant_id=tenant_id,
        title=title,
        filename=filename,
        content_type=content_type,
        status=status_value,
        priority=priority,
        raw_text=content,
    )
    db.add(document)
    db.flush()
    for index, chunk in enumerate(chunk_text(content)):
        db.add(DocumentChunk(tenant_id=tenant_id, document_id=document.id, chunk_index=index, content=chunk, token_count=len(chunk.split()), source_ref=f"{filename}#{index}"))
    db.commit()
    db.refresh(document)
    return document


def require_local_persistence() -> None:
    settings = get_settings()
    if settings.persistence_mode == "operational":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Context persistence is delegated to flowkron-operational-service.",
        )


def ensure_base_forms(db: Session, tenant_id: str) -> None:
    for code, fields in BASE_FORMS.items():
        exists = db.scalar(select(BusinessContextForm.id).where(BusinessContextForm.tenant_id == tenant_id, BusinessContextForm.code == code))
        if exists:
            continue
        form = BusinessContextForm(tenant_id=tenant_id, code=code, name=code.replace("-", " ").title(), description=f"Formulario base {code}")
        db.add(form)
        db.flush()
        for position, field_name in enumerate(fields):
            db.add(BusinessContextField(form_id=form.id, name=field_name, label=field_name.replace("_", " ").title(), position=position))
    db.commit()


@router.post("/documents/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(payload: DocumentCreate, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    return persist_context_document(
        tenant_id=tenant.tenant_id,
        title=payload.title,
        filename=payload.filename,
        content=payload.content,
        content_type=payload.content_type,
        status_value=payload.status,
        priority=payload.priority,
        db=db,
    )


@router.post("/documents/upload-file", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document_file(
    title: str = Form(...),
    status_value: str = Form("active", alias="status"),
    priority: int = Form(100),
    file: UploadFile = File(...),
    tenant: TenantContext = Depends(resolve_tenant),
    db: Session = Depends(get_db),
):
    filename = file.filename or "context-document"
    extension = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
    if extension not in get_settings().allowed_upload_extensions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported context document extension")
    raw_content = await file.read()
    if len(raw_content) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Context document exceeds max upload size")
    try:
        content = extract_text_from_upload(filename, raw_content)
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if not content.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Context document does not contain extractable text")
    return persist_context_document(
        tenant_id=tenant.tenant_id,
        title=title,
        filename=filename,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        status_value=status_value,
        priority=priority,
        db=db,
    )


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.persistence_mode == "operational":
        return operational_context_client.list_documents(tenant.tenant_id)
    require_local_persistence()
    return db.scalars(select(BusinessContextDocument).where(BusinessContextDocument.tenant_id == tenant.tenant_id).order_by(BusinessContextDocument.id)).all()


@router.get("/status", response_model=BusinessContextStatusRead)
def get_context_status(tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.persistence_mode == "operational":
        return operational_context_client.get_status(tenant.tenant_id)
    require_local_persistence()
    documents = [
        _document_payload(document)
        for document in db.scalars(select(BusinessContextDocument).where(BusinessContextDocument.tenant_id == tenant.tenant_id).order_by(BusinessContextDocument.id)).all()
    ]
    return _status_from_documents(documents)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    document = db.get(BusinessContextDocument, document_id)
    if not document or document.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def patch_document(document_id: int, payload: DocumentPatch, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    document = get_document(document_id, tenant, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    db.commit()
    db.refresh(document)
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    document = get_document(document_id, tenant, db)
    db.delete(document)
    db.commit()


@router.get("/templates", response_model=list[TemplateRead])
def list_templates():
    return list_context_template_groups()


@router.get("/templates/{template_id}")
def get_template(template_id: int):
    template = get_context_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.get("/templates/{template_id}/download")
def download_template(template_id: int):
    template = get_context_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    content, filename, media_type = render_template_file(template)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/forms", response_model=list[FormRead])
def list_forms(tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    ensure_base_forms(db, tenant.tenant_id)
    return db.scalars(select(BusinessContextForm).options(selectinload(BusinessContextForm.fields)).where(BusinessContextForm.tenant_id == tenant.tenant_id).order_by(BusinessContextForm.id)).all()


@router.get("/forms/submissions", response_model=list[FormSubmissionRead])
def list_submissions(tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    return db.scalars(select(BusinessContextFormSubmission).where(BusinessContextFormSubmission.tenant_id == tenant.tenant_id).order_by(BusinessContextFormSubmission.id)).all()


@router.get("/forms/{form_id}", response_model=FormRead)
def get_form(form_id: int, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    form = db.scalar(select(BusinessContextForm).options(selectinload(BusinessContextForm.fields)).where(BusinessContextForm.id == form_id, BusinessContextForm.tenant_id == tenant.tenant_id))
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


@router.post("/forms/{form_id}/submit", response_model=FormSubmissionRead, status_code=status.HTTP_201_CREATED)
def submit_form(form_id: int, payload: FormSubmissionCreate, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    get_form(form_id, tenant, db)
    submission = BusinessContextFormSubmission(tenant_id=tenant.tenant_id, form_id=form_id, payload=payload.payload)
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission
