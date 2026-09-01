import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.body_metric_log import BodyMetricLog
from app.models.user import User

router = APIRouter(prefix="/api/body-metrics", tags=["body-metrics"])


class BodyMetricRequest(BaseModel):
    weight_kg: float
    notes: str | None = None

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v):
        if not (30 <= v <= 300):
            raise ValueError("Weight must be between 30 and 300 kg.")
        return v


class BodyMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    logged_at: datetime
    weight_kg: float
    notes: str | None


@router.post("", response_model=BodyMetricOut)
def log_body_weight(
    payload: BodyMetricRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    entry = BodyMetricLog(user_id=user.id, weight_kg=payload.weight_kg, notes=payload.notes)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=list[BodyMetricOut])
def list_body_weight(
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    return (
        db.query(BodyMetricLog)
        .filter(BodyMetricLog.user_id == user.id)
        .order_by(BodyMetricLog.logged_at)
        .all()
    )


@router.delete("/{entry_id}")
def delete_body_weight(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    entry = db.query(BodyMetricLog).filter(BodyMetricLog.id == entry_id, BodyMetricLog.user_id == user.id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(entry)
    db.commit()
    return {"success": True}
