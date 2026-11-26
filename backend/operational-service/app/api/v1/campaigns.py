from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.campaign import (
    CampaignApproveIn,
    CampaignCreateIn,
    CampaignDispatchOut,
    CampaignOut,
    CampaignStateIn,
    ChannelConnectionCreateIn,
    ChannelConnectionOut,
    ChannelConnectionRotateIn,
    ChannelReceiptIn,
    ChannelReceiptOut,
    ConversationEmailIn,
    ConversationEmailOut,
    TemplateCreateIn,
    TemplateOut,
    UnsubscribeIn,
    UnsubscribeOut,
    UnsubscribeTokenCreateIn,
    UnsubscribeTokenOut,
)
from app.services.campaign_service import (
    approve_campaign,
    create_campaign,
    create_template_with_version,
    ingest_channel_receipt,
    issue_unsubscribe_token,
    process_campaign_stub_batch,
    record_public_unsubscribe,
    redeem_unsubscribe_token,
    set_campaign_state,
)
from app.services.channel_connection_service import (
    create_channel_connection,
    list_channel_connections,
    revoke_channel_connection,
    rotate_channel_connection,
    send_conversation_email,
)


router = APIRouter(prefix="/api/v1", tags=["Campaigns & Channels"])


@router.get("/channels/connections", response_model=list[ChannelConnectionOut])
def connections_list(
    channel: Literal["email", "whatsapp"] | None = None,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_channel_connections(db, tenant, channel=channel)


@router.post("/channels/connections", response_model=ChannelConnectionOut, status_code=status.HTTP_201_CREATED)
def connections_create(
    payload: ChannelConnectionCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_channel_connection(
        db,
        tenant,
        channel=payload.channel,
        provider=payload.provider,
        sender_address=payload.sender_address,
        display_name=payload.display_name,
        verified=payload.verified,
        sandbox_only=payload.sandbox_only,
        provider_secret=payload.provider_secret,
        actor_user_id=principal.user_id,
    )


@router.post("/channels/connections/{connection_id}/rotate", response_model=ChannelConnectionOut)
def connections_rotate(
    connection_id: int,
    payload: ChannelConnectionRotateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return rotate_channel_connection(
        db, tenant, connection_id, new_provider_secret=payload.new_provider_secret, actor_user_id=principal.user_id,
    )


@router.post("/channels/connections/{connection_id}/revoke", response_model=ChannelConnectionOut)
def connections_revoke(
    connection_id: int,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return revoke_channel_connection(db, tenant, connection_id, actor_user_id=principal.user_id)


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def templates_create(
    payload: TemplateCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_template_with_version(
        db,
        tenant,
        name=payload.name,
        channel=payload.channel,
        language=payload.language,
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
        declared_variables=payload.declared_variables,
        approve_immediately=payload.approve_immediately,
        actor_user_id=principal.user_id,
    )


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def campaigns_create(
    payload: CampaignCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return create_campaign(
        db,
        tenant,
        name=payload.name,
        channel=payload.channel,
        purpose=payload.purpose,
        template_version_id=payload.template_version_id,
        connection_id=payload.connection_id,
        segment_filter=payload.segment_filter,
        timezone_iana=payload.timezone_iana,
        actor_user_id=principal.user_id,
    )


@router.post("/campaigns/{campaign_id}/approve", response_model=CampaignOut)
def campaigns_approve(
    campaign_id: int,
    payload: CampaignApproveIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return approve_campaign(
        db,
        tenant,
        campaign_id,
        expected_version=payload.expected_version,
        actor_user_id=principal.user_id,
        scheduled_at=payload.scheduled_at,
    )


@router.post("/campaigns/{campaign_id}/{action}", response_model=CampaignOut)
def campaigns_transition(
    campaign_id: int,
    action: Literal["pause", "resume", "cancel"],
    payload: CampaignStateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return set_campaign_state(db, tenant, campaign_id, action=action, expected_version=payload.expected_version)


@router.post("/campaigns/dispatch-stub", response_model=CampaignDispatchOut)
def campaigns_dispatch_stub(
    limit: int = Query(default=20, ge=1, le=50),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return process_campaign_stub_batch(db, tenant, limit=limit)


@router.post("/channels/receipts", response_model=ChannelReceiptOut)
def channels_receipts(
    payload: ChannelReceiptIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return ingest_channel_receipt(
        db,
        tenant,
        provider_account_id=payload.provider_account_id,
        provider_event_id=payload.provider_event_id,
        event_type=payload.event_type,
        provider_message_id=payload.provider_message_id,
        destination=payload.destination,
        payload=payload.payload,
        occurred_at=payload.occurred_at,
    )


@router.post("/channels/unsubscribe", response_model=UnsubscribeOut)
def channels_unsubscribe(
    payload: UnsubscribeIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return record_public_unsubscribe(
        db, tenant, channel=payload.channel, destination=payload.destination, purpose=payload.purpose,
    )


@router.post("/channels/unsubscribe-tokens", response_model=UnsubscribeTokenOut, status_code=status.HTTP_201_CREATED)
def channels_issue_unsubscribe_token(
    payload: UnsubscribeTokenCreateIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    _ = principal
    return issue_unsubscribe_token(
        db,
        tenant,
        channel=payload.channel,
        destination=payload.destination,
        purpose=payload.purpose,
        client_id=payload.client_id,
        ttl_days=payload.ttl_days,
    )


@router.post("/public/channels/unsubscribe/{token}", response_model=UnsubscribeOut)
def public_channels_unsubscribe(
    token: str,
    db: Session = Depends(get_db),
):
    return redeem_unsubscribe_token(db, token)


@router.post(
    "/conversations/{conversation_id}/email",
    response_model=ConversationEmailOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def conversation_send_email(
    conversation_id: int,
    payload: ConversationEmailIn,
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return send_conversation_email(
        db,
        tenant,
        conversation_id,
        connection_id=payload.connection_id,
        to_email=payload.to_email,
        subject=payload.subject,
        body_text=payload.body_text,
        idempotency_key=payload.idempotency_key,
        actor_user_id=principal.user_id,
    )
