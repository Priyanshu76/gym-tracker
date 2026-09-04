"""
Full-account JSON export/import — "your data, yours to keep," matching
openGym's own stated philosophy on data ownership. Distinct from the CSV
export on Workout Logs (that's for reading/sharing history with a coach;
this is a complete machine-readable backup covering everything except
authentication internals).
"""
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.body_metric_log import BodyMetricLog
from app.models.custom_exercise import CustomExercise
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.workout_log import WorkoutLog
from app.models.workout_plan import PlanDay, PlanExercise, WorkoutPlan

router = APIRouter(prefix="/api/export", tags=["export"])


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


@router.get("/full")
def export_full_account(
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Everything tied to this account, in one JSON document — profile,
    full workout history, body-weight log, custom exercises, and plans
    (by exercise NAME, not internal id, so the file is portable at all).
    Never includes password_hash or session tokens.
    """
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    logs = db.query(WorkoutLog).filter(WorkoutLog.user_id == user.id).order_by(WorkoutLog.logged_at).all()
    body_metrics = db.query(BodyMetricLog).filter(BodyMetricLog.user_id == user.id).order_by(BodyMetricLog.logged_at).all()
    custom_exercises = db.query(CustomExercise).filter(CustomExercise.user_id == user.id).all()
    plans = db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id).all()

    return {
        "export_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {"username": user.username, "display_name": user.display_name},
        "profile": None if not profile else {
            "goal": profile.goal.value, "experience_level": profile.experience_level.value,
            "equipment_access": profile.equipment_access.value, "height_cm": float(profile.height_cm),
            "weight_kg": float(profile.weight_kg),
            "goal_weight_kg": float(profile.goal_weight_kg) if profile.goal_weight_kg else None,
            "age": profile.age, "days_per_week": profile.days_per_week,
            "injuries_limitations": profile.injuries_limitations,
        },
        "workout_logs": [
            {
                "workout_date": _json_safe(log.workout_date), "day_name": log.day_name,
                "section": log.section.value, "exercise": log.exercise, "performed_as": log.performed_as,
                "muscle_group": log.muscle_group, "set_number": log.set_number,
                "weight_kg": float(log.weight_kg) if log.weight_kg is not None else None,
                "reps": log.reps, "duration_seconds": log.duration_seconds,
                "rpe": float(log.rpe) if log.rpe is not None else None, "set_type": log.set_type.value,
                "metrics": log.metrics,
            }
            for log in logs
        ],
        "body_metrics": [
            {"logged_at": _json_safe(m.logged_at), "weight_kg": float(m.weight_kg), "notes": m.notes}
            for m in body_metrics
        ],
        "custom_exercises": [
            {"main_exercise": c.main_exercise, "custom_alt_name": c.custom_alt_name}
            for c in custom_exercises
        ],
        "plans": [
            {
                "name": plan.name, "default_progression_rule": plan.default_progression_rule.value,
                "days": [
                    {
                        "day_index": d.day_index, "day_name": d.day_name, "split_label": d.split_label,
                        "is_rest": d.is_rest,
                        "exercises": [
                            {
                                "exercise_name": pe.exercise.name, "order_index": pe.order_index,
                                "sets": pe.sets, "reps_low": pe.reps_low, "reps_high": pe.reps_high,
                                "progression_rule": pe.progression_rule.value if pe.progression_rule else None,
                            }
                            for pe in d.exercises
                        ],
                    }
                    for d in plan.days
                ],
            }
            for plan in plans
        ],
    }


class PlanImportRequest(BaseModel):
    name: str
    default_progression_rule: str = "linear"
    days: list[dict]


@router.post("/workout-history/import")
async def import_workout_history(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Bulk-imports workout history from another tracker's CSV export.
    Auto-detects FitNotes, Strong, or Hevy format from the header row —
    each confirmed against real sample exports (see app/services/importers.py).
    Every imported row lands in section='Main'; exercise names are stored
    exactly as they appeared in the source file (WorkoutLog.exercise is
    already a free-text field, so no library-matching step is needed here,
    unlike plan import which does need to resolve real Exercise rows).
    """
    import csv
    import io

    from app.models.exercise import Exercise
    from app.services.importers import PARSERS, detect_source

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not read this file as UTF-8 text — is it a CSV export?")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="Empty or unreadable CSV file.")

    source = detect_source(list(reader.fieldnames))
    if not source:
        raise HTTPException(
            status_code=400,
            detail="Unrecognized file format — this importer supports FitNotes, Strong, and Hevy CSV exports.",
        )

    rows = list(reader)
    imported_sets = PARSERS[source](rows)
    if not imported_sets:
        return {"success": True, "detected_source": source, "imported_count": 0, "message": "No valid rows found in the file."}

    # Best-effort muscle_group enrichment by exact exercise-name match
    # against the shared library — not required for the import to
    # succeed, just a nice-to-have when the name happens to match exactly.
    exercise_lookup = {ex.name: ex.muscle_group for ex in db.query(Exercise).all()}

    for s in imported_sets:
        db.add(WorkoutLog(
            user_id=user.id, workout_date=s.workout_date, day_name=s.workout_date.strftime("%A"),
            section="Main", exercise=s.exercise_name, muscle_group=exercise_lookup.get(s.exercise_name),
            set_number=s.set_number, weight_kg=s.weight_kg, reps=s.reps,
            duration_seconds=s.duration_seconds, rpe=s.rpe, set_type=s.set_type,
            metrics={"imported_notes": s.notes} if s.notes else None,
        ))
    db.commit()

    return {"success": True, "detected_source": source, "imported_count": len(imported_sets)}


@router.post("/plans/import")
def import_plan(
    payload: PlanImportRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Imports a shared plan as a brand-new inactive plan for the current
    user — never overwrites anything they already have, matching openGym's
    'importing merges' behavior. Exercises are matched by NAME against the
    shared library; any name that doesn't match is skipped with a warning
    rather than failing the whole import.
    """
    from app.models.exercise import Exercise
    from app.models.workout_plan import ProgressionRule

    try:
        default_rule = ProgressionRule(payload.default_progression_rule)
    except ValueError:
        default_rule = ProgressionRule.linear

    plan = WorkoutPlan(user_id=user.id, name=payload.name, is_active=False, default_progression_rule=default_rule)
    db.add(plan)
    db.flush()

    skipped_exercises = []
    for day in payload.days:
        plan_day = PlanDay(
            plan_id=plan.id, day_index=day.get("day_index", 0), day_name=day.get("day_name", ""),
            split_label=day.get("split_label", ""), is_rest=day.get("is_rest", False),
        )
        db.add(plan_day)
        db.flush()
        for ex in day.get("exercises", []):
            exercise_row = db.query(Exercise).filter(Exercise.name == ex.get("exercise_name")).first()
            if not exercise_row:
                skipped_exercises.append(ex.get("exercise_name"))
                continue
            prog_rule = None
            if ex.get("progression_rule"):
                try:
                    prog_rule = ProgressionRule(ex["progression_rule"])
                except ValueError:
                    prog_rule = None
            db.add(PlanExercise(
                plan_day_id=plan_day.id, exercise_id=exercise_row.id, order_index=ex.get("order_index", 0),
                sets=ex.get("sets", 3), reps_low=ex.get("reps_low", 8), reps_high=ex.get("reps_high", 12),
                progression_rule=prog_rule,
            ))
    db.commit()

    return {"success": True, "plan_id": str(plan.id), "skipped_exercises": skipped_exercises}
