import uuid
from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.workout_log import Section, SetType


class LogSetRequest(BaseModel):
    workout_date: date_type
    day_name: str
    section: Section = Section.main
    exercise: str
    performed_as: str | None = None
    muscle_group: str | None = None
    set_number: int | None = None
    weight_kg: float | None = None
    reps: int | None = None
    duration_seconds: int | None = None
    rpe: float | None = None  # 1.0-10.0
    set_type: SetType = SetType.working
    metrics: dict | None = None  # Warmup/Stretch generic fields — replaces the old fixed Field1-3 columns

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, v):
        if v is not None and not (0 <= v <= 3600):
            raise ValueError("Duration must be between 0 and 3600 seconds.")
        return v

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v, info):
        if info.data.get("section") == Section.main and v is not None and not (0 <= v <= 500):
            raise ValueError("Weight must be between 0 and 500 kg.")
        return v

    @field_validator("reps")
    @classmethod
    def validate_reps(cls, v, info):
        if info.data.get("section") == Section.main and v is not None and not (0 <= v <= 100):
            raise ValueError("Reps must be between 0 and 100.")
        return v

    @field_validator("rpe")
    @classmethod
    def validate_rpe(cls, v):
        if v is not None and not (1 <= v <= 10):
            raise ValueError("RPE must be between 1 and 10.")
        return v


class LogSetResponse(BaseModel):
    success: bool
    message: str
    is_pr: bool = False
    pr_type: str | None = None  # "weight" or "estimated_1rm" — None when is_pr is False


class WorkoutLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    logged_at: datetime
    workout_date: date_type
    day_name: str
    section: Section
    exercise: str
    performed_as: str | None
    muscle_group: str | None
    set_number: int | None
    weight_kg: float | None
    reps: int | None
    duration_seconds: int | None
    rpe: float | None
    set_type: SetType
    metrics: dict | None
