import uuid

from pydantic import BaseModel, ConfigDict


class PlanExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID  # the PlanExercise row's own id — needed to call evaluate-progression
    exercise_id: uuid.UUID
    order_index: int
    sets: int
    reps_low: int
    reps_high: int
    name: str
    muscle_group: str | None
    progression_rule: str | None
    current_weight_kg: float | None
    current_reps_target: int | None
    last_progression_note: str | None
    superset_group_id: uuid.UUID | None


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
