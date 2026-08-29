import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal


class ProfileRequest(BaseModel):
    goal: Goal
    experience_level: ExperienceLevel
    equipment_access: EquipmentAccess
    height_cm: float
    weight_kg: float
    age: int
    days_per_week: int
    injuries_limitations: str | None = None

    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, v):
        if not (100 <= v <= 250):
            raise ValueError("Height must be between 100 and 250 cm.")
        return v

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v):
        if not (30 <= v <= 300):
            raise ValueError("Weight must be between 30 and 300 kg.")
        return v

    @field_validator("age")
    @classmethod
    def validate_age(cls, v):
        if not (13 <= v <= 100):
            raise ValueError("Age must be between 13 and 100.")
        return v

    @field_validator("days_per_week")
    @classmethod
    def validate_days(cls, v):
        if not (3 <= v <= 6):
            raise ValueError("Days per week must be between 3 and 6.")
        return v


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    goal: Goal
    experience_level: ExperienceLevel
    equipment_access: EquipmentAccess
    height_cm: float
    weight_kg: float
    age: int
    days_per_week: int
    injuries_limitations: str | None
    updated_at: datetime
