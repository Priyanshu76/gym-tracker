import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.schemas.auth import MessageResponse
from app.schemas.workout import LogSetRequest, WorkoutLogOut

router = APIRouter(prefix="/api", tags=["workouts"])


@router.post("/workout-logs", response_model=MessageResponse)
def log_set(
    payload: LogSetRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    log = WorkoutLog(
        user_id=user.id,
        workout_date=payload.workout_date,
        day_name=payload.day_name,
        section=payload.section,
        exercise=payload.exercise,
        performed_as=payload.performed_as,
        muscle_group=payload.muscle_group,
        set_number=payload.set_number,
        weight_kg=payload.weight_kg,
        reps=payload.reps,
        metrics=payload.metrics,
    )
    db.add(log)
    db.commit()
    return MessageResponse(success=True, message="Set logged.")


@router.get("/workout-logs", response_model=list[WorkoutLogOut])
def get_progress(
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    return (
        db.query(WorkoutLog)
        .filter(WorkoutLog.user_id == user.id)
        .order_by(WorkoutLog.logged_at)
        .all()
    )


@router.patch("/workout-logs/{log_id}", response_model=WorkoutLogOut)
def edit_workout_log(
    log_id: uuid.UUID,
    payload: LogSetRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    log = db.query(WorkoutLog).filter(WorkoutLog.id == log_id, WorkoutLog.user_id == user.id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found or does not belong to this account")

    log.workout_date = payload.workout_date
    log.day_name = payload.day_name
    log.section = payload.section
    log.exercise = payload.exercise
    log.performed_as = payload.performed_as
    log.muscle_group = payload.muscle_group
    log.set_number = payload.set_number
    log.weight_kg = payload.weight_kg
    log.reps = payload.reps
    log.metrics = payload.metrics
    db.commit()
    db.refresh(log)
    return log


@router.delete("/workout-logs/{log_id}", response_model=MessageResponse)
def delete_workout_log(
    log_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    log = db.query(WorkoutLog).filter(WorkoutLog.id == log_id, WorkoutLog.user_id == user.id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found or does not belong to this account")
    db.delete(log)
    db.commit()
    return MessageResponse(success=True, message="Entry deleted.")
