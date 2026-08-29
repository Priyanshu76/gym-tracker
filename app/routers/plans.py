import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.user_profile import UserProfile
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
                        exercise_id=pe.exercise_id, order_index=pe.order_index, sets=pe.sets,
                        reps_low=pe.reps_low, reps_high=pe.reps_high,
                        name=pe.exercise.name, muscle_group=pe.exercise.muscle_group,
                    )
                    for pe in day.exercises
                ],
            )
            for day in plan.days
        ],
    )


@router.post("/generate", response_model=list[PlanDetailOut])
def generate_plans(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete your profile before generating a plan.")

    options = generate_plan_options(profile, db, num_options=3, extra_seed=str(uuid.uuid4()))

    saved_plans = []
    for option in options:
        plan = WorkoutPlan(user_id=user.id, name=option.name, is_active=False)
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
