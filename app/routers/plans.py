import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.workout_log import WorkoutLog
from app.models.workout_plan import PlanDay, PlanExercise, WorkoutPlan
from app.schemas.plan import PlanDayOut, PlanDetailOut, PlanExerciseOut, PlanSummaryOut
from app.services.plan_generator import generate_plan_options

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _plan_to_detail(plan: WorkoutPlan) -> PlanDetailOut:
    return PlanDetailOut(
        id=plan.id, name=plan.name, is_active=plan.is_active,
        days=[
            PlanDayOut(
                day_index=day.day_index, day_name=day.day_name, split_label=day.split_label, is_rest=day.is_rest,
                exercises=[
                    PlanExerciseOut(
                        id=pe.id,
                        exercise_id=pe.exercise_id, order_index=pe.order_index, sets=pe.sets,
                        reps_low=pe.reps_low, reps_high=pe.reps_high,
                        name=pe.exercise.name, muscle_group=pe.exercise.muscle_group,
                        progression_rule=(pe.progression_rule or plan.default_progression_rule).value,
                        current_weight_kg=float(pe.current_weight_kg) if pe.current_weight_kg is not None else None,
                        current_reps_target=pe.current_reps_target if pe.current_reps_target is not None else pe.reps_low,
                        last_progression_note=pe.last_progression_note,
                        superset_group_id=pe.superset_group_id,
                    )
                    for pe in day.exercises
                ],
            )
            for day in plan.days
        ],
    )


@router.post("/plan-exercises/{plan_exercise_id}/evaluate-progression")
def evaluate_progression_endpoint(
    plan_exercise_id: uuid.UUID,
    workout_date: date | None = None,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Runs the progression engine for one exercise after a session, using
    whatever sets were logged for it on `workout_date` (defaults to the
    most recent date this exercise has any Main-section logs for). Persists
    the new prescription and returns it, including a human-readable note —
    every target should say why it's that number, not just what it is.
    """
    from app.models.exercise import EquipmentAccess
    from app.services.progression import (
        SetResult,
        evaluate_double_progression,
        evaluate_greyskull_lp,
        evaluate_linear,
    )

    pe = (
        db.query(PlanExercise)
        .join(PlanDay)
        .join(WorkoutPlan)
        .filter(PlanExercise.id == plan_exercise_id, WorkoutPlan.user_id == user.id)
        .first()
    )
    if not pe:
        raise HTTPException(status_code=404, detail="Plan exercise not found")

    plan = db.query(WorkoutPlan).join(PlanDay).filter(PlanDay.id == pe.plan_day_id).first()
    rule = pe.progression_rule or plan.default_progression_rule

    if workout_date is None:
        last_date_row = (
            db.query(WorkoutLog.workout_date)
            .filter(WorkoutLog.user_id == user.id, WorkoutLog.exercise == pe.exercise.name, WorkoutLog.section == "Main")
            .order_by(WorkoutLog.workout_date.desc())
            .first()
        )
        if not last_date_row:
            raise HTTPException(status_code=400, detail="No logged sets found for this exercise yet.")
        workout_date = last_date_row[0]

    logs = (
        db.query(WorkoutLog)
        .filter(
            WorkoutLog.user_id == user.id, WorkoutLog.exercise == pe.exercise.name,
            WorkoutLog.workout_date == workout_date, WorkoutLog.section == "Main",
            WorkoutLog.set_type == "working",  # warmup/drop/etc. sets never drive progression
        )
        .order_by(WorkoutLog.set_number)
        .all()
    )
    if not logs:
        raise HTTPException(status_code=400, detail="No working sets found for this exercise on that date.")

    is_bodyweight = pe.exercise.equipment_needed == EquipmentAccess.bodyweight_only
    sets_performed = [SetResult(reps=log.reps, weight_kg=float(log.weight_kg) if log.weight_kg else None) for log in logs]

    # Establish a baseline on first-ever evaluation, so the very first
    # logged session sets the starting point rather than requiring the user
    # to have pre-configured a weight before they'd even tried the exercise.
    if pe.current_weight_kg is None and not is_bodyweight:
        pe.current_weight_kg = sets_performed[0].weight_kg or 0
    if pe.current_reps_target is None:
        pe.current_reps_target = pe.reps_low

    current_weight = float(pe.current_weight_kg) if pe.current_weight_kg is not None else 0.0

    if rule.value == "none":
        raise HTTPException(status_code=400, detail="This exercise is set to manual progression — nothing to evaluate.")
    elif rule.value == "linear":
        result = evaluate_linear(
            current_weight_kg=current_weight, target_reps=pe.current_reps_target,
            sets_performed=sets_performed, consecutive_misses=pe.consecutive_misses, is_bodyweight=is_bodyweight,
        )
    elif rule.value == "greyskull_lp":
        result = evaluate_greyskull_lp(
            current_weight_kg=current_weight, target_reps=pe.current_reps_target,
            sets_performed=sets_performed, consecutive_misses=pe.consecutive_misses,
        )
    else:  # double_progression
        result = evaluate_double_progression(
            current_weight_kg=current_weight, rep_range_low=pe.reps_low, rep_range_high=pe.reps_high,
            current_reps_target=pe.current_reps_target, sets_performed=sets_performed,
        )

    pe.current_weight_kg = result.new_weight_kg
    pe.current_reps_target = result.new_reps_target
    pe.consecutive_misses = result.new_consecutive_misses
    pe.last_progression_note = result.note
    db.commit()

    return {
        "outcome": result.outcome,
        "note": result.note,
        "new_weight_kg": result.new_weight_kg,
        "new_reps_target": result.new_reps_target,
    }


@router.patch("/plan-exercises/pair-superset")
def pair_superset(
    plan_exercise_id_a: uuid.UUID,
    plan_exercise_id_b: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Pairs two exercises within the same plan day as a superset — logged
    back-to-back with a rest only after the pair, not between them. Pairs
    only for now, not arbitrary N-way groups.
    """
    if plan_exercise_id_a == plan_exercise_id_b:
        raise HTTPException(status_code=400, detail="Can't pair an exercise with itself.")

    pe_a = db.query(PlanExercise).join(PlanDay).join(WorkoutPlan).filter(
        PlanExercise.id == plan_exercise_id_a, WorkoutPlan.user_id == user.id
    ).first()
    pe_b = db.query(PlanExercise).join(PlanDay).join(WorkoutPlan).filter(
        PlanExercise.id == plan_exercise_id_b, WorkoutPlan.user_id == user.id
    ).first()
    if not pe_a or not pe_b:
        raise HTTPException(status_code=404, detail="One or both exercises not found")
    if pe_a.plan_day_id != pe_b.plan_day_id:
        raise HTTPException(status_code=400, detail="Both exercises must be on the same day to be paired.")

    new_group_id = uuid.uuid4()
    pe_a.superset_group_id = new_group_id
    pe_b.superset_group_id = new_group_id
    db.commit()
    return {"success": True, "superset_group_id": str(new_group_id)}


@router.patch("/plan-exercises/{plan_exercise_id}/unpair-superset")
def unpair_superset(
    plan_exercise_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Dissolves the WHOLE group this exercise belongs to, not just this one
    row — a superset only makes sense as a pair, so removing one side
    degrades both back to independent singles."""
    pe = db.query(PlanExercise).join(PlanDay).join(WorkoutPlan).filter(
        PlanExercise.id == plan_exercise_id, WorkoutPlan.user_id == user.id
    ).first()
    if not pe:
        raise HTTPException(status_code=404, detail="Plan exercise not found")

    if pe.superset_group_id:
        db.query(PlanExercise).filter(PlanExercise.superset_group_id == pe.superset_group_id).update(
            {"superset_group_id": None}
        )
        db.commit()
    return {"success": True}


@router.post("/generate", response_model=list[PlanDetailOut])
def generate_plans(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    from app.models.workout_plan import ProgressionRule

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete your profile before generating a plan.")

    # Goal-appropriate default progression scheme — greyskull_lp rewards the
    # heavy-compound, low-rep style strength training favors; double
    # progression through a rep range is the standard hypertrophy approach;
    # the rest default to plain linear, which is simpler and appropriate
    # when the goal isn't primarily about programmed overload.
    default_rule = {
        "strength": ProgressionRule.greyskull_lp,
        "hypertrophy": ProgressionRule.double_progression,
    }.get(profile.goal.value, ProgressionRule.linear)

    options = generate_plan_options(profile, db, num_options=3, extra_seed=str(uuid.uuid4()))

    saved_plans = []
    for option in options:
        plan = WorkoutPlan(user_id=user.id, name=option.name, is_active=False, default_progression_rule=default_rule)
        db.add(plan)
        db.flush()
        for day in option.days:
            plan_day = PlanDay(
                plan_id=plan.id, day_index=day.day_index, day_name=day.day_name,
                split_label=day.split_label, is_rest=day.is_rest,
            )
            db.add(plan_day)
            db.flush()
            for i, ge in enumerate(day.exercises):
                db.add(PlanExercise(
                    plan_day_id=plan_day.id, exercise_id=ge.exercise.id, order_index=i,
                    sets=ge.sets, reps_low=ge.reps_low, reps_high=ge.reps_high,
                ))
        db.commit()
        db.refresh(plan)
        saved_plans.append(plan)

    # re-fetch with joins loaded for serialization
    ids = [p.id for p in saved_plans]
    full_plans = (
        db.query(WorkoutPlan)
        .options(joinedload(WorkoutPlan.days).joinedload(PlanDay.exercises).joinedload(PlanExercise.exercise))
        .filter(WorkoutPlan.id.in_(ids))
        .all()
    )
    order = {pid: i for i, pid in enumerate(ids)}
    full_plans.sort(key=lambda p: order[p.id])
    return [_plan_to_detail(p) for p in full_plans]


@router.get("", response_model=list[PlanSummaryOut])
def list_plans(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    plans = db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id).order_by(WorkoutPlan.created_at.desc()).all()
    return [PlanSummaryOut(id=p.id, name=p.name, is_active=p.is_active) for p in plans]


@router.get("/active", response_model=PlanDetailOut | None)
def get_active_plan(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    plan = (
        db.query(WorkoutPlan)
        .options(joinedload(WorkoutPlan.days).joinedload(PlanDay.exercises).joinedload(PlanExercise.exercise))
        .filter(WorkoutPlan.user_id == user.id, WorkoutPlan.is_active.is_(True))
        .first()
    )
    return _plan_to_detail(plan) if plan else None


@router.patch("/deactivate", response_model=dict)
def deactivate_current_plan(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    """Reverts to the classic fixed plan — the log page falls back to it
    whenever GET /api/plans/active returns null."""
    db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id, WorkoutPlan.is_active.is_(True)).update({"is_active": False})
    db.commit()
    return {"success": True}


@router.patch("/{plan_id}/activate", response_model=PlanDetailOut)
def activate_plan(plan_id: uuid.UUID, user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    plan = db.query(WorkoutPlan).filter(WorkoutPlan.id == plan_id, WorkoutPlan.user_id == user.id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id).update({"is_active": False})
    plan.is_active = True
    db.commit()

    full_plan = (
        db.query(WorkoutPlan)
        .options(joinedload(WorkoutPlan.days).joinedload(PlanDay.exercises).joinedload(PlanExercise.exercise))
        .filter(WorkoutPlan.id == plan.id)
        .first()
    )
    return _plan_to_detail(full_plan)
