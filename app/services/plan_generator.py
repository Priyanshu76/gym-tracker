"""
Rules-based weekly workout plan generator. Deterministic and testable —
given the same profile and variant seed, always produces the same plan.

Deliberately NOT an LLM: a bad plan here is a physical-injury risk, not a UX
annoyance, and a rules engine can guarantee it never selects an exercise
outside the user's equipment/experience bounds. See the architecture
discussion for the full reasoning.
"""
import random

from sqlalchemy.orm import Session as DBSession

from app.models.exercise import EQUIPMENT_RANK, EXPERIENCE_RANK, Exercise, SplitCategory
from app.models.user_profile import UserProfile
from app.models.workout_log import Section

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# split_label -> which split_categories to draw from, and how many exercises per category
SPLIT_TEMPLATES = {
    3: [("Full Body", {"push": 2, "pull": 2, "legs": 2, "core": 1})] * 3,
    4: [
        ("Upper", {"push": 3, "pull": 3}),
        ("Lower", {"legs": 5, "core": 1}),
        ("Upper", {"push": 3, "pull": 3}),
        ("Lower", {"legs": 5, "core": 1}),
    ],
    5: [
        ("Push", {"push": 5, "core": 1}),
        ("Pull", {"pull": 5, "core": 1}),
        ("Legs", {"legs": 6}),
        ("Upper", {"push": 3, "pull": 3}),
        ("Lower", {"legs": 5, "core": 1}),
    ],
    6: [
        ("Push", {"push": 5, "core": 1}),
        ("Pull", {"pull": 5, "core": 1}),
        ("Legs", {"legs": 6}),
        ("Push", {"push": 5, "core": 1}),
        ("Pull", {"pull": 5, "core": 1}),
        ("Legs", {"legs": 6}),
    ],
}


class GeneratedExercise:
    def __init__(self, exercise: Exercise, sets: int, reps_low: int, reps_high: int):
        self.exercise = exercise
        self.sets = sets
        self.reps_low = reps_low
        self.reps_high = reps_high


class GeneratedDay:
    def __init__(self, day_index: int, day_name: str, split_label: str, is_rest: bool, exercises: list[GeneratedExercise]):
        self.day_index = day_index
        self.day_name = day_name
        self.split_label = split_label
        self.is_rest = is_rest
        self.exercises = exercises


class GeneratedPlan:
    def __init__(self, name: str, days: list[GeneratedDay]):
        self.name = name
        self.days = days


def _eligible_exercises(db: DBSession, profile: UserProfile, split_category: str) -> list[Exercise]:
    equipment_rank = EQUIPMENT_RANK[profile.equipment_access]
    experience_rank = EXPERIENCE_RANK[profile.experience_level]

    candidates = (
        db.query(Exercise)
        .filter(Exercise.category == Section.main, Exercise.split_category == SplitCategory(split_category))
        .all()
    )
    return [
        ex for ex in candidates
        if profile.goal.value in ex.suitable_goals
        and EQUIPMENT_RANK[ex.equipment_needed] <= equipment_rank
        and EXPERIENCE_RANK[ex.min_experience_level] <= experience_rank
    ]


def _adjust_reps_for_goal(exercise: Exercise, goal: str) -> tuple[int, int, int]:
    """Goal-specific rep/set targets take priority over the exercise's own
    stored default range, which reflects its *typical* usage, not what this
    particular user is training for."""
    if goal == "strength":
        return 4, 4, 8
    if goal == "endurance" or goal == "fat_loss":
        return 3, 12, 20
    # hypertrophy / general_fitness fall back to the exercise's own curated range
    return exercise.default_sets, exercise.default_reps_low, exercise.default_reps_high


def generate_plan_options(profile: UserProfile, db: DBSession, num_options: int = 3, extra_seed: str = "") -> list[GeneratedPlan]:
    """
    extra_seed lets the caller control reproducibility: the API endpoint
    passes a fresh random value on every call, so hitting "Generate new
    options" twice actually gives different results — this was flagged as
    a bug (repeated generation always returned the same plan) because the
    original seed was purely (user_id, variant), which is great for tests
    but wrong for the product. Tests pass a fixed extra_seed to keep
    verifying determinism given identical inputs.
    """
    template = SPLIT_TEMPLATES[profile.days_per_week]
    rest_days_needed = 7 - len(template)

    options = []
    for variant in range(num_options):
        rng = random.Random(f"{profile.user_id}-{variant}-{extra_seed}")
        days = []
        day_idx = 0

        for split_label, category_counts in template:
            exercises: list[GeneratedExercise] = []
            for split_category, count in category_counts.items():
                pool = _eligible_exercises(db, profile, split_category)
                rng.shuffle(pool)
                # rotate the starting point per variant so options 1/2/3 differ
                # even when pulling from the same eligible pool
                rotated = pool[variant % max(len(pool), 1):] + pool[:variant % max(len(pool), 1)]
                chosen = rotated[:count]
                for ex in chosen:
                    sets, reps_low, reps_high = _adjust_reps_for_goal(ex, profile.goal.value)
                    exercises.append(GeneratedExercise(ex, sets, reps_low, reps_high))
            days.append(GeneratedDay(day_idx, DAY_NAMES[day_idx], split_label, is_rest=False, exercises=exercises))
            day_idx += 1

        # remaining days in the week are rest days
        for _ in range(rest_days_needed):
            days.append(GeneratedDay(day_idx, DAY_NAMES[day_idx], "Rest", is_rest=True, exercises=[]))
            day_idx += 1

        name = f"{profile.goal.value.replace('_', ' ').title()} Plan — Option {variant + 1}"
        options.append(GeneratedPlan(name=name, days=days))

    return options
