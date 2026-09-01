import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.custom_exercise import CustomExercise
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.exercise import AddExerciseRequest, CustomExerciseOut

router = APIRouter(prefix="/api", tags=["exercises"])


@router.get("/exercises/search")
def search_exercise_library(
    q: str | None = None,
    equipment: str | None = None,
    category: str = "Main",
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Searches the shared 58-exercise library — replaces the old
    curated-alternates-only swap flow with a real browsable/searchable
    library, matching openGym's equipment-filtered exercise search.

    Defaults the equipment filter to the user's own stated profile access
    if they have one and didn't explicitly override it — "the options
    adapt to what you've picked" per openGym's own description, rather
    than showing exercises the user told us they can't do.
    """
    from app.models.exercise import EQUIPMENT_RANK, Exercise, EquipmentAccess
    from app.models.user_profile import UserProfile

    equipment_tier = equipment
    if equipment_tier is None:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if profile:
            equipment_tier = profile.equipment_access.value

    query = db.query(Exercise).filter(Exercise.category == category)
    if q:
        query = query.filter(Exercise.name.ilike(f"%{q}%"))
    results = query.order_by(Exercise.name).all()

    if equipment_tier:
        try:
            max_rank = EQUIPMENT_RANK[EquipmentAccess(equipment_tier)]
            results = [ex for ex in results if EQUIPMENT_RANK[ex.equipment_needed] <= max_rank]
        except ValueError:
            pass  # unrecognized equipment value — ignore the filter rather than 400 on a minor typo

    return [
        {
            "id": str(ex.id), "name": ex.name, "muscle_group": ex.muscle_group,
            "equipment_needed": ex.equipment_needed.value, "split_category": ex.split_category.value if ex.split_category else None,
            "is_timed": ex.is_timed, "is_unilateral": ex.is_unilateral,
        }
        for ex in results[:30]
    ]


@router.post("/custom-exercises", response_model=CustomExerciseOut)
def add_exercise(
    payload: AddExerciseRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    exercise = CustomExercise(
        user_id=user.id,
        main_exercise=payload.main_exercise,
        custom_alt_name=payload.custom_alt_name,
    )
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


@router.get("/custom-exercises", response_model=list[CustomExerciseOut])
def get_custom_exercises(
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    return (
        db.query(CustomExercise)
        .filter(CustomExercise.user_id == user.id, CustomExercise.active.is_(True))
        .all()
    )


@router.delete("/custom-exercises/{exercise_id}", response_model=MessageResponse)
def remove_exercise(
    exercise_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    # Filtering by user_id in the same query IS the ownership check — there's
    # no separate "look it up, then check who owns it" step to get wrong, unlike
    # the n8n version where that was a manually-built extra chain of nodes.
    exercise = (
        db.query(CustomExercise)
        .filter(CustomExercise.id == exercise_id, CustomExercise.user_id == user.id)
        .first()
    )
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found or does not belong to this account")

    exercise.active = False
    db.commit()
    return MessageResponse(success=True, message="Exercise removed.")
