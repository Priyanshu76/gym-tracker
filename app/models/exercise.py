import enum
import uuid

from sqlalchemy import ARRAY, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal
from app.models.workout_log import Section


class MovementPattern(str, enum.Enum):
    compound = "compound"
    isolation = "isolation"


class SplitCategory(str, enum.Enum):
    push = "push"
    pull = "pull"
    legs = "legs"
    core = "core"


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category: Mapped[Section] = mapped_column(Enum(Section), nullable=False, default=Section.main)

    muscle_group: Mapped[str | None] = mapped_column(String(60), nullable=True)
    movement_pattern: Mapped[MovementPattern | None] = mapped_column(Enum(MovementPattern), nullable=True)
    # Used by the plan generator to build Push/Pull/Legs/Upper/Lower/Full-Body
    # day templates — deliberately separate from the free-text muscle_group,
    # which is for display, not for reliable programmatic matching.
    split_category: Mapped[SplitCategory | None] = mapped_column(Enum(SplitCategory), nullable=True)

    # Minimum tier required — an exercise needing full_gym can't be selected
    # for a user whose equipment_access is home_basic or bodyweight_only.
    equipment_needed: Mapped[EquipmentAccess] = mapped_column(Enum(EquipmentAccess), nullable=False)
    min_experience_level: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False, default=ExperienceLevel.beginner)

    # Which goals this exercise is a good fit for — the generator filters/scores on this.
    suitable_goals: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    default_sets: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    default_reps_low: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    default_reps_high: Mapped[int] = mapped_column(Integer, nullable=False, default=12)


EQUIPMENT_RANK = {
    EquipmentAccess.bodyweight_only: 0,
    EquipmentAccess.home_basic: 1,
    EquipmentAccess.full_gym: 2,
}

EXPERIENCE_RANK = {
    ExperienceLevel.beginner: 0,
    ExperienceLevel.intermediate: 1,
    ExperienceLevel.advanced: 2,
}
