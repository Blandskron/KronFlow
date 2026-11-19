from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import enforce_ingest_rate_limit
from app.core.tenant_resolver import TenantContext
from app.schemas.whatsapp_turn import TurnClaimIn, TurnCompleteIn, TurnOut, TurnPrepareIn, TurnReceiptIn, TurnTokenIn
from app.services.whatsapp_turn_service import begin_turn_send, claim_turn, complete_turn, prepare_turn, read_turn, reconcile_turn, release_turn


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/turns", tags=["WhatsApp Turns"], dependencies=[Depends(private_response)])


@router.post("/claim", response_model=TurnOut)
def claim(payload: TurnClaimIn, tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return claim_turn(db, tenant, payload)


@router.get("/{turn_id}", response_model=TurnOut)
def read(turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return read_turn(db, tenant, turn_id)


@router.post("/{turn_id}/prepare", response_model=TurnOut)
def prepare(payload: TurnPrepareIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return prepare_turn(db, tenant, turn_id, payload)


@router.post("/{turn_id}/begin-send", response_model=TurnOut)
def begin_send(payload: TurnTokenIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return begin_turn_send(db, tenant, turn_id, payload.claim_token)


@router.post("/{turn_id}/complete", response_model=TurnOut)
def complete(payload: TurnCompleteIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return complete_turn(db, tenant, turn_id, payload)


@router.post("/{turn_id}/release", response_model=TurnOut)
def release(payload: TurnTokenIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return release_turn(db, tenant, turn_id, payload.claim_token)


@router.post("/{turn_id}/reconcile", response_model=TurnOut)
def reconcile(payload: TurnReceiptIn, turn_id: int = Path(gt=0), tenant: TenantContext = Depends(enforce_ingest_rate_limit), db: Session = Depends(get_db)):
    return reconcile_turn(db, tenant, turn_id, payload)
