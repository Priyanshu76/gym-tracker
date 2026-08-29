from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.profile import ProfileOut, ProfileRequest

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profile", response_model=ProfileOut | None)
def get_profile(user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    return db.query(UserProfile).filter(UserProfile.user_id == user.id).first()


@router.put("/profile", response_model=ProfileOut)
def upsert_profile(
    payload: ProfileRequest,
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile:
        for field, value in payload.model_dump().items():
            setattr(profile, field, value)
    else:
        profile = UserProfile(user_id=user.id, **payload.model_dump())
        db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
