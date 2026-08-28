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
