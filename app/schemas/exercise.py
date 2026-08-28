import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AddExerciseRequest(BaseModel):
    main_exercise: str
    custom_alt_name: str


class CustomExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    main_exercise: str
    custom_alt_name: str
    created_at: datetime
