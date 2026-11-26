"""Webchat widget administration and public origin-pinned visitor session/message endpoints."""

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.webchat import (
    WebchatMessageCreateIn,
    WebchatMessageListOut,
    WebchatMessagePostOut,
    WebchatSessionCreateIn,
    WebchatSessionOut,
    WebchatWidgetCreateIn,
    WebchatWidgetOut,
    WebchatWidgetUpdateIn,
)
from app.services.webchat_service import (
    create_webchat_session,
    create_webchat_widget,
    list_webchat_messages,
    list_webchat_widgets,
    post_webchat_message,
    update_webchat_widget,
)


router = APIRouter(prefix="/api/v1", tags=["Webchat"])


@router.get("/webchat/widgets", response_model=list[WebchatWidgetOut])
def list_widgets_endpoint(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_webchat_widgets(db, tenant)


@router.post("/webchat/widgets", response_model=WebchatWidgetOut, status_code=status.HTTP_201_CREATED)
def create_widget_endpoint(
    payload: WebchatWidgetCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return create_webchat_widget(db, tenant, payload, actor_user_id=principal.user_id)


@router.patch("/webchat/widgets/{widget_id}", response_model=WebchatWidgetOut)
def update_widget_endpoint(
    widget_id: int,
    payload: WebchatWidgetUpdateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return update_webchat_widget(db, tenant, widget_id, payload)


@router.post("/public/webchat/{widget_key}/sessions", response_model=WebchatSessionOut, status_code=status.HTTP_201_CREATED)
def public_webchat_create_session(
    widget_key: str,
    payload: WebchatSessionCreateIn,
    request: Request,
    origin: str | None = Header(default=None, alias="Origin"),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    return create_webchat_session(
        db,
        widget_key=widget_key,
        origin=origin,
        visitor_name=payload.visitor_name,
        visitor_email=payload.visitor_email,
        client_ip=client_ip,
    )


@router.post("/public/webchat/{widget_key}/messages", response_model=WebchatMessagePostOut)
def public_webchat_post_message(
    widget_key: str,
    payload: WebchatMessageCreateIn,
    origin: str | None = Header(default=None, alias="Origin"),
    session_token: str | None = Header(default=None, alias="X-Webchat-Session"),
    db: Session = Depends(get_db),
):
    return post_webchat_message(
        db,
        widget_key=widget_key,
        session_token=session_token,
        origin=origin,
        body=payload.body,
        idempotency_key=payload.idempotency_key,
    )


@router.get("/public/webchat/{widget_key}/messages", response_model=WebchatMessageListOut)
def public_webchat_list_messages(
    widget_key: str,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    origin: str | None = Header(default=None, alias="Origin"),
    session_token: str | None = Header(default=None, alias="X-Webchat-Session"),
    db: Session = Depends(get_db),
):
    return list_webchat_messages(
        db,
        widget_key=widget_key,
        session_token=session_token,
        origin=origin,
        after_id=after_id,
        limit=limit,
    )
