import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProgressionRule(str, enum.Enum):
    none = "none"  # manual — user enters their own weight every time, no auto-progression
    linear = "linear"
    greyskull_lp = "greyskull_lp"
    double_progression = "double_progression"


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_progression_rule: Mapped[ProgressionRule] = mapped_column(Enum(ProgressionRule), nullable=False, default=ProgressionRule.linear)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    days: Mapped[list["PlanDay"]] = relationship(back_populates="plan", cascade="all, delete-orphan", order_by="PlanDay.day_index")


class PlanDay(Base):
    __tablename__ = "plan_days"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workout_plans.id", ondelete="CASCADE"), nullable=False)

    day_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-6, Monday=0
    day_name: Mapped[str] = mapped_column(String(20), nullable=False)
    split_label: Mapped[str] = mapped_column(String(30), nullable=False)  # "Push", "Pull", "Legs", "Upper", "Lower", "Full Body", "Rest"
    is_rest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    plan: Mapped["WorkoutPlan"] = relationship(back_populates="days")
    exercises: Mapped[list["PlanExercise"]] = relationship(back_populates="plan_day", cascade="all, delete-orphan", order_by="PlanExercise.order_index")


class PlanExercise(Base):
    __tablename__ = "plan_exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_day_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_days.id", ondelete="CASCADE"), nullable=False)
    exercise_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)

    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    reps_low: Mapped[int] = mapped_column(Integer, nullable=False)
    reps_high: Mapped[int] = mapped_column(Integer, nullable=False)

    # Progression state — None per-exercise means "inherit the plan's default".
    # current_weight_kg/current_reps_target are the LIVE prescription the
    # engine updates after each logged session; reps_low/reps_high above
    # stay fixed as the exercise's original designed range.
    progression_rule: Mapped[ProgressionRule | None] = mapped_column(Enum(ProgressionRule), nullable=True)
    current_weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    current_reps_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consecutive_misses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_progression_note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    plan_day: Mapped["PlanDay"] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship()
