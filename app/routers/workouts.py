import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.schemas.auth import MessageResponse
from app.schemas.workout import LogSetRequest, LogSetResponse, WorkoutLogOut

router = APIRouter(prefix="/api", tags=["workouts"])


def _estimated_1rm(weight_kg: float, reps: int) -> float:
    """Epley formula — same one already used client-side on the dashboard."""
    return weight_kg * (1 + reps / 30)


def _check_pr(db: DBSession, user_id, exercise: str, weight_kg: float | None, reps: int | None) -> tuple[bool, str | None]:
    """
    Checks a just-logged set against every PRIOR working set for the same
    exercise (Main section only). Weight-based PR detection only — a
    bodyweight exercise with no weight_kg is excluded here rather than
    guessing at a reps-based PR definition that wasn't asked for.
    """
    if weight_kg is None or reps is None:
        return False, None

    prior_sets = (
        db.query(WorkoutLog.weight_kg, WorkoutLog.reps)
        .filter(
            WorkoutLog.user_id == user_id, WorkoutLog.exercise == exercise,
            WorkoutLog.section == "Main", WorkoutLog.set_type == "working",
            WorkoutLog.weight_kg.isnot(None), WorkoutLog.reps.isnot(None),
        )
        .all()
    )
    if not prior_sets:
        return False, None  # first-ever set for this exercise isn't a "PR" — nothing to beat yet

    prior_max_weight = max(float(w) for w, r in prior_sets)
    prior_max_1rm = max(_estimated_1rm(float(w), r) for w, r in prior_sets)

    new_1rm = _estimated_1rm(weight_kg, reps)
    if weight_kg > prior_max_weight:
        return True, "weight"
    if new_1rm > prior_max_1rm:
        return True, "estimated_1rm"
    return False, None


@router.post("/workout-logs", response_model=LogSetResponse)
def log_set(
    payload: LogSetRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    is_pr, pr_type = False, None
    if payload.section == "Main" and payload.set_type == "working":
        is_pr, pr_type = _check_pr(db, user.id, payload.exercise, payload.weight_kg, payload.reps)

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
        duration_seconds=payload.duration_seconds,
        reps=payload.reps,
        rpe=payload.rpe,
        set_type=payload.set_type,
        metrics=payload.metrics,
    )
    db.add(log)
    db.commit()
    return LogSetResponse(success=True, message="Set logged.", is_pr=is_pr, pr_type=pr_type)


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


@router.get("/workout-logs/export")
def export_workout_logs_csv(
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """CSV export of full workout history — for backup or sharing with a
    coach, explicitly missing per the platform analysis."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    logs = (
        db.query(WorkoutLog)
        .filter(WorkoutLog.user_id == user.id)
        .order_by(WorkoutLog.logged_at)
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "date", "day", "section", "exercise", "performed_as", "muscle_group",
        "set_number", "weight_kg", "reps", "rpe", "set_type", "metrics",
    ])
    for log in logs:
        writer.writerow([
            log.workout_date, log.day_name, log.section.value, log.exercise,
            log.performed_as or "", log.muscle_group or "", log.set_number or "",
            log.weight_kg or "", log.reps or "", log.rpe or "", log.set_type.value,
            log.metrics or "",
        ])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=workout_history.csv"},
    )


@router.get("/workout-logs/last", response_model=list[WorkoutLogOut])
def get_last_session_for_exercise(
    exercise: str,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Powers the 'last time you did this' reference and the 'repeat last
    workout' autofill — both explicitly missing per the platform analysis.
    Returns every set from the most recent date this exercise was logged,
    not just one row, since a full session usually has multiple sets.
    """
    last_date_row = (
        db.query(WorkoutLog.workout_date)
        .filter(WorkoutLog.user_id == user.id, WorkoutLog.exercise == exercise, WorkoutLog.section == "Main")
        .order_by(WorkoutLog.workout_date.desc())
        .first()
    )
    if not last_date_row:
        return []
    last_date = last_date_row[0]
    return (
        db.query(WorkoutLog)
        .filter(WorkoutLog.user_id == user.id, WorkoutLog.exercise == exercise, WorkoutLog.workout_date == last_date)
        .order_by(WorkoutLog.set_number)
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
    log.duration_seconds = payload.duration_seconds
    log.reps = payload.reps
    log.rpe = payload.rpe
    log.set_type = payload.set_type
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
