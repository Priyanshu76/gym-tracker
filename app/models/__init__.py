"""
Import every model here so Base.metadata is fully populated — Alembic's
autogenerate relies on this to detect the full schema.
"""
from app.models.body_metric_log import BodyMetricLog  # noqa: F401
from app.models.custom_exercise import CustomExercise  # noqa: F401
from app.models.exercise import Exercise  # noqa: F401
from app.models.pending_signup import PendingSignup  # noqa: F401
from app.models.session import Session  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_profile import UserProfile  # noqa: F401
from app.models.workout_log import WorkoutLog  # noqa: F401
from app.models.workout_plan import PlanDay, PlanExercise, WorkoutPlan  # noqa: F401
