import enum
import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Section(str, enum.Enum):
    main = "Main"
    warmup = "Warmup"
    stretch = "Stretch"


class SetType(str, enum.Enum):
    working = "working"
    warmup = "warmup"
    drop_set = "drop_set"
    amrap = "amrap"
    failure = "failure"


class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    workout_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    day_name: Mapped[str] = mapped_column(String(10), nullable=False)
    section: Mapped[Section] = mapped_column(Enum(Section), nullable=False, default=Section.main)

    exercise: Mapped[str] = mapped_column(String(100), nullable=False)
    performed_as: Mapped[str | None] = mapped_column(String(100), nullable=True)
    muscle_group: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Main-lift fields
    set_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # timed exercises (planks, holds) log this instead of reps
    rpe: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)  # 1.0-10.0, RPE/RIR scale
    set_type: Mapped[SetType] = mapped_column(Enum(SetType), nullable=False, default=SetType.working)

    # Warmup/Stretch fields — the old Field1-3 Label/Value columns collapse into
    # one JSON column here; Postgres's JSONB lets us query into it if needed
    # later, and we're not stuck with a fixed "3 fields max" ceiling anymore.
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="workout_logs")
