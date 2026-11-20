from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import enforce_ingest_rate_limit
from app.core.tenant_resolver import TenantContext
from app.schemas.whatsapp_turn import (
    TurnClaimIn, TurnCompleteIn, TurnEnqueueIn, TurnEnqueueOut, TurnNextIn, TurnNextOut,
    TurnOut, TurnPrepareIn, TurnReceiptIn, TurnSendIn, TurnTokenIn,
)
from app.services.whatsapp_turn_service import (
    begin_turn_send, claim_next_turn, claim_turn, complete_turn, enqueue_turn, prepare_turn,
    read_turn, reconcile_turn, release_turn, retry_turn_job,
)


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/turns", tags=["WhatsApp Turns"], dependencies=[Depends(private_response)])


@router.post("/claim", response_model=TurnOut)
def claim(payload: TurnClaimIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return claim_turn(db, tenant, payload)


@router.post("/enqueue", response_model=TurnEnqueueOut, status_code=202)
def enqueue(payload: TurnEnqueueIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return enqueue_turn(db, tenant, payload)


@router.post("/next", response_model=TurnNextOut)
def next_job(payload: TurnNextIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return claim_next_turn(db, tenant, payload.account_key)


@router.post("/{turn_id}/retry", response_model=TurnOut)
def retry_job(payload: TurnNextIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return retry_turn_job(db, tenant, turn_id, payload.account_key)


@router.get("/{turn_id}", response_model=TurnOut)
def read(turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return read_turn(db, tenant, turn_id)


@router.post("/{turn_id}/prepare", response_model=TurnOut)
def prepare(payload: TurnPrepareIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return prepare_turn(db, tenant, turn_id, payload)


@router.post("/{turn_id}/begin-send", response_model=TurnOut)
def begin_send(payload: TurnSendIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return begin_turn_send(db, tenant, turn_id, payload.claim_token, payload.provider_message_id)


@router.post("/{turn_id}/complete", response_model=TurnOut)
def complete(payload: TurnCompleteIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return complete_turn(db, tenant, turn_id, payload)


@router.post("/{turn_id}/release", response_model=TurnOut)
def release(payload: TurnTokenIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return release_turn(db, tenant, turn_id, payload.claim_token)


@router.post("/{turn_id}/reconcile", response_model=TurnOut)
def reconcile(payload: TurnReceiptIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return reconcile_turn(db, tenant, turn_id, payload)
