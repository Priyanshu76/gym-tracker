import uuid

from pydantic import BaseModel, ConfigDict


class PlanExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    exercise_id: uuid.UUID
    order_index: int
    sets: int
    reps_low: int
    reps_high: int
    name: str
    muscle_group: str | None


class PlanDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    day_index: int
    day_name: str
    split_label: str
    is_rest: bool
    exercises: list[PlanExerciseOut]


class PlanSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    is_active: bool


class PlanDetailOut(PlanSummaryOut):
    days: list[PlanDayOut]
