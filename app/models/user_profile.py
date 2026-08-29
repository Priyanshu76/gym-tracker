import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Goal(str, enum.Enum):
    strength = "strength"
    hypertrophy = "hypertrophy"
    fat_loss = "fat_loss"
    endurance = "endurance"
    general_fitness = "general_fitness"


class ExperienceLevel(str, enum.Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class EquipmentAccess(str, enum.Enum):
    full_gym = "full_gym"
    home_basic = "home_basic"  # dumbbells/bands, no machines/barbell
    bodyweight_only = "bodyweight_only"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    goal: Mapped[Goal] = mapped_column(Enum(Goal), nullable=False)
    experience_level: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False)
    equipment_access: Mapped[EquipmentAccess] = mapped_column(Enum(EquipmentAccess), nullable=False)

    height_cm: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    weight_kg: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)

    days_per_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 3-6, drives split selection
    injuries_limitations: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="profile")
