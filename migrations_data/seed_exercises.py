"""
Seeds the exercise library that the plan generator selects from. This
replaces the old hardcoded DATA array in weekly_lift_log.html as the source
of truth for what exercises exist — that array is now only used for the
"classic" fixed plan (kept, per product decision, as an alternative to
personalized generation), while this table drives everything dynamic.

Idempotent: safe to re-run, skips any exercise name that already exists.

Usage: python -m migrations_data.seed_exercises
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models.exercise import Exercise  # noqa: E402
from app.models.workout_log import Section  # noqa: E402

# Maps exercise name -> push/pull/legs/core, used by the plan generator to
# build day templates. Kept separate from the tuple list below rather than
# adding an 11th positional field to every row — lower risk of transposition
# errors, and easy to audit/extend independently.
SPLIT_CATEGORY_MAP = {
    # Legs
    "Barbell Back Squat": "legs", "Goblet Squat": "legs", "Bodyweight Squat": "legs",
    "Romanian Deadlift": "legs", "Dumbbell Romanian Deadlift": "legs", "Leg Press": "legs",
    "Bulgarian Split Squat": "legs", "Walking Lunge": "legs", "Leg Curl": "legs",
    "Leg Extension": "legs", "Standing Calf Raise": "legs", "Calf Raise (Bodyweight)": "legs",
    "Kettlebell Swing": "legs", "Burpee": "legs", "Jump Rope": "legs",
    # Push (chest, shoulders-press, triceps)
    "Barbell Bench Press": "push", "Dumbbell Bench Press": "push", "Push-Up": "push",
    "Incline Dumbbell Press": "push", "Cable Fly": "push", "Dumbbell Fly": "push",
    "Seated Dumbbell Shoulder Press": "push", "Barbell Overhead Press": "push", "Pike Push-Up": "push",
    "Dumbbell Lateral Raise": "push", "Close-Grip Bench Press": "push", "Triceps Dip": "push",
    "Rope Pushdown": "push", "Overhead Dumbbell Extension": "push",
    # Pull (back, rear delts, biceps)
    "Pull-Up": "pull", "Lat Pulldown": "pull", "Barbell Row": "pull", "Dumbbell Row": "pull",
    "Seated Cable Row": "pull", "Inverted Row": "pull", "Reverse Pec Deck": "pull",
    "Cable Face Pull": "pull", "Barbell Curl": "pull", "Dumbbell Curl": "pull", "Hammer Curl": "pull",
    # Core
    "Hanging Leg Raise": "core", "Reverse Crunch": "core", "Cable Crunch": "core",
    "Bodyweight Crunch": "core", "Ab Wheel Rollout": "core", "Plank": "core", "Mountain Climber": "core",
}

# Logged by elapsed time instead of reps.
TIMED_EXERCISES = {"Plank"}
# Logged as total reps, displayed/labeled as a per-side split.
UNILATERAL_EXERCISES = {"Walking Lunge", "Bulgarian Split Squat"}

# (name, category, muscle_group, movement_pattern, equipment_needed, min_experience,
#  suitable_goals, sets, reps_low, reps_high)
G_STR, G_HYP, G_FAT, G_END, G_GEN = "strength", "hypertrophy", "fat_loss", "endurance", "general_fitness"
BW, HOME, GYM = "bodyweight_only", "home_basic", "full_gym"
BEG, INT, ADV = "beginner", "intermediate", "advanced"
COMPOUND, ISOLATION = "compound", "isolation"
MAIN, WARMUP, STRETCH = Section.main, Section.warmup, Section.stretch

EXERCISES = [
    # --- Legs ---
    ("Barbell Back Squat", MAIN, "Quads + Glutes", COMPOUND, GYM, BEG, [G_STR, G_HYP, G_GEN], 4, 4, 8),
    ("Goblet Squat", MAIN, "Quads + Glutes", COMPOUND, HOME, BEG, [G_STR, G_HYP, G_GEN, G_FAT], 3, 8, 12),
    ("Bodyweight Squat", MAIN, "Quads + Glutes", COMPOUND, BW, BEG, [G_STR, G_HYP, G_GEN, G_FAT, G_END], 3, 12, 20),
    ("Romanian Deadlift", MAIN, "Hamstrings + Glutes", COMPOUND, GYM, INT, [G_STR, G_HYP], 3, 6, 10),
    ("Dumbbell Romanian Deadlift", MAIN, "Hamstrings + Glutes", COMPOUND, HOME, BEG, [G_STR, G_HYP, G_GEN], 3, 8, 12),
    ("Leg Press", MAIN, "Quads + Glutes", COMPOUND, GYM, BEG, [G_HYP, G_GEN], 3, 8, 12),
    ("Bulgarian Split Squat", MAIN, "Quads + Glutes", COMPOUND, HOME, BEG, [G_HYP, G_STR, G_FAT], 3, 8, 12),
    ("Walking Lunge", MAIN, "Quads + Glutes", COMPOUND, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 3, 12, 16),
    ("Leg Curl", MAIN, "Hamstrings", ISOLATION, GYM, BEG, [G_HYP], 3, 10, 15),
    ("Leg Extension", MAIN, "Quadriceps", ISOLATION, GYM, BEG, [G_HYP], 3, 10, 15),
    ("Standing Calf Raise", MAIN, "Calves", ISOLATION, GYM, BEG, [G_HYP, G_GEN], 3, 10, 20),
    ("Calf Raise (Bodyweight)", MAIN, "Calves", ISOLATION, BW, BEG, [G_GEN, G_END], 3, 15, 25),

    # --- Chest ---
    ("Barbell Bench Press", MAIN, "Chest", COMPOUND, GYM, BEG, [G_STR, G_HYP], 4, 4, 8),
    ("Dumbbell Bench Press", MAIN, "Chest", COMPOUND, HOME, BEG, [G_STR, G_HYP, G_GEN], 3, 8, 12),
    ("Push-Up", MAIN, "Chest", COMPOUND, BW, BEG, [G_STR, G_HYP, G_GEN, G_FAT, G_END], 3, 10, 20),
    ("Incline Dumbbell Press", MAIN, "Upper Chest", COMPOUND, HOME, BEG, [G_HYP], 3, 8, 12),
    ("Cable Fly", MAIN, "Chest", ISOLATION, GYM, INT, [G_HYP], 3, 10, 15),
    ("Dumbbell Fly", MAIN, "Chest", ISOLATION, HOME, INT, [G_HYP], 3, 10, 15),

    # --- Back ---
    ("Pull-Up", MAIN, "Lats", COMPOUND, BW, INT, [G_STR, G_HYP, G_GEN], 3, 5, 10),
    ("Lat Pulldown", MAIN, "Lats", COMPOUND, GYM, BEG, [G_HYP, G_GEN], 3, 8, 12),
    ("Barbell Row", MAIN, "Mid-Back + Lats", COMPOUND, GYM, BEG, [G_STR, G_HYP], 3, 6, 10),
    ("Dumbbell Row", MAIN, "Lats + Mid-Back", COMPOUND, HOME, BEG, [G_STR, G_HYP, G_GEN], 3, 8, 12),
    ("Seated Cable Row", MAIN, "Mid-Back", COMPOUND, GYM, BEG, [G_HYP], 3, 8, 12),
    ("Inverted Row", MAIN, "Mid-Back", COMPOUND, BW, BEG, [G_STR, G_HYP, G_GEN, G_FAT], 3, 10, 15),

    # --- Shoulders ---
    ("Seated Dumbbell Shoulder Press", MAIN, "Front + Lateral Delts", COMPOUND, HOME, BEG, [G_STR, G_HYP, G_GEN], 3, 6, 10),
    ("Barbell Overhead Press", MAIN, "Shoulders", COMPOUND, GYM, BEG, [G_STR, G_HYP], 4, 4, 8),
    ("Pike Push-Up", MAIN, "Shoulders", COMPOUND, BW, INT, [G_GEN, G_FAT], 3, 8, 12),
    ("Dumbbell Lateral Raise", MAIN, "Lateral Delts", ISOLATION, HOME, BEG, [G_HYP], 3, 10, 15),
    ("Reverse Pec Deck", MAIN, "Rear Delts", ISOLATION, GYM, BEG, [G_HYP], 3, 10, 15),
    ("Cable Face Pull", MAIN, "Rear Delts", ISOLATION, GYM, BEG, [G_HYP, G_GEN], 3, 10, 15),

    # --- Arms ---
    ("Barbell Curl", MAIN, "Biceps", ISOLATION, GYM, BEG, [G_HYP], 3, 8, 12),
    ("Dumbbell Curl", MAIN, "Biceps", ISOLATION, HOME, BEG, [G_HYP, G_GEN], 3, 8, 12),
    ("Hammer Curl", MAIN, "Brachialis", ISOLATION, HOME, BEG, [G_HYP], 3, 8, 12),
    ("Close-Grip Bench Press", MAIN, "Triceps", COMPOUND, GYM, INT, [G_STR, G_HYP], 3, 6, 10),
    ("Triceps Dip", MAIN, "Triceps", COMPOUND, BW, INT, [G_STR, G_HYP, G_GEN], 3, 8, 12),
    ("Rope Pushdown", MAIN, "Triceps", ISOLATION, GYM, BEG, [G_HYP], 3, 10, 15),
    ("Overhead Dumbbell Extension", MAIN, "Triceps", ISOLATION, HOME, BEG, [G_HYP], 3, 10, 15),

    # --- Core ---
    ("Hanging Leg Raise", MAIN, "Lower Abs", ISOLATION, GYM, INT, [G_HYP, G_GEN], 3, 10, 15),
    ("Reverse Crunch", MAIN, "Lower Abs", ISOLATION, BW, BEG, [G_GEN, G_FAT], 3, 12, 20),
    ("Cable Crunch", MAIN, "Abs", ISOLATION, GYM, BEG, [G_HYP], 3, 10, 15),
    ("Bodyweight Crunch", MAIN, "Abs", ISOLATION, BW, BEG, [G_GEN, G_FAT, G_END], 3, 15, 25),
    ("Ab Wheel Rollout", MAIN, "Core", COMPOUND, HOME, ADV, [G_STR, G_HYP], 3, 8, 15),
    ("Plank", MAIN, "Core", ISOLATION, BW, BEG, [G_GEN, G_FAT, G_END], 3, 30, 60),

    # --- Endurance / fat-loss friendly conditioning movements (main category, high rep) ---
    ("Kettlebell Swing", MAIN, "Full Body", COMPOUND, HOME, INT, [G_FAT, G_END], 3, 15, 20),
    ("Burpee", MAIN, "Full Body", COMPOUND, BW, INT, [G_FAT, G_END], 3, 10, 15),
    ("Jump Rope", MAIN, "Full Body", COMPOUND, BW, BEG, [G_FAT, G_END], 3, 30, 60),
    ("Mountain Climber", MAIN, "Full Body", COMPOUND, BW, BEG, [G_FAT, G_END], 3, 20, 30),

    # --- Warmup ---
    ("Treadmill", WARMUP, None, None, GYM, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 5, 10),
    ("Stationary Bike", WARMUP, None, None, GYM, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 5, 10),
    ("Jumping Jacks", WARMUP, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 2),
    ("Arm Circles", WARMUP, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 1),
    ("Bodyweight Squat (Warmup)", WARMUP, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 2, 10, 15),

    # --- Stretch / finishing ---
    ("Quad Stretch", STRETCH, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 1),
    ("Hamstring Stretch", STRETCH, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 1),
    ("Chest Doorway Stretch", STRETCH, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 1),
    ("Child's Pose", STRETCH, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 1),
    ("Shoulder Cross-Body Stretch", STRETCH, None, None, BW, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 1),
    ("Foam Rolling", STRETCH, None, None, HOME, BEG, [G_STR, G_HYP, G_FAT, G_END, G_GEN], 1, 1, 1),
]


def seed():
    db = SessionLocal()
    created, skipped = 0, 0
    try:
        for row in EXERCISES:
            name = row[0]
            if db.query(Exercise).filter(Exercise.name == name).first():
                skipped += 1
                continue
            (_, category, muscle_group, movement_pattern, equipment_needed,
             min_experience, suitable_goals, sets, reps_low, reps_high) = row
            db.add(Exercise(
                name=name, category=category, muscle_group=muscle_group,
                split_category=SPLIT_CATEGORY_MAP.get(name),
                movement_pattern=movement_pattern, equipment_needed=equipment_needed,
                min_experience_level=min_experience, suitable_goals=suitable_goals,
                default_sets=sets, default_reps_low=reps_low, default_reps_high=reps_high,
                is_timed=name in TIMED_EXERCISES, is_unilateral=name in UNILATERAL_EXERCISES,
            ))
            created += 1
        db.commit()
        print(f"Seeded {created} exercises, skipped {skipped} already present.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
