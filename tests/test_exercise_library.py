import pytest

from app.database import Base, engine, SessionLocal
from app.models.exercise import Exercise
from app.models.user_profile import EquipmentAccess, ExperienceLevel, Goal
from app.models.workout_log import Section
from migrations_data.seed_exercises import seed


@pytest.fixture(autouse=True)
def clean_and_seed():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield


def test_seed_creates_all_categories():
    db = SessionLocal()
    assert db.query(Exercise).filter(Exercise.category == Section.main).count() > 30
    assert db.query(Exercise).filter(Exercise.category == Section.warmup).count() >= 5
    assert db.query(Exercise).filter(Exercise.category == Section.stretch).count() >= 5
    db.close()


def test_seed_is_idempotent():
    db = SessionLocal()
    before = db.query(Exercise).count()
    db.close()
    seed()  # run again
    db = SessionLocal()
    after = db.query(Exercise).count()
    db.close()
    assert before == after, "re-running the seed script must not create duplicates"


def test_every_goal_has_enough_main_exercises_at_every_equipment_tier():
    """This is the coverage guarantee the plan generator (Phase C) depends
    on — if any (goal, equipment) combination has too few exercises, the
    generator can't build a full week for someone with that profile."""
    db = SessionLocal()
    main_exercises = db.query(Exercise).filter(Exercise.category == Section.main).all()
    db.close()

    for goal in Goal:
        for equipment in EquipmentAccess:
            equipment_rank = {"bodyweight_only": 0, "home_basic": 1, "full_gym": 2}
            matching = [
                ex for ex in main_exercises
                if goal.value in ex.suitable_goals
                and equipment_rank[ex.equipment_needed.value] <= equipment_rank[equipment.value]
            ]
            assert len(matching) >= 6, (
                f"Only {len(matching)} exercises available for goal={goal.value}, "
                f"equipment={equipment.value} — need at least 6 for a real weekly plan"
            )


def test_every_main_exercise_has_a_muscle_group():
    db = SessionLocal()
    main_exercises = db.query(Exercise).filter(Exercise.category == Section.main).all()
    db.close()
    for ex in main_exercises:
        assert ex.muscle_group, f"{ex.name} is missing a muscle_group"


def test_beginner_exercises_exist_for_every_goal():
    db = SessionLocal()
    main_exercises = db.query(Exercise).filter(
        Exercise.category == Section.main,
        Exercise.min_experience_level == ExperienceLevel.beginner,
    ).all()
    db.close()
    for goal in Goal:
        matching = [ex for ex in main_exercises if goal.value in ex.suitable_goals]
        assert len(matching) >= 4, f"Not enough beginner-safe exercises for goal={goal.value}"
