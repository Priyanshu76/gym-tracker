"""
Tests the migration script's transformation logic against plain dicts shaped
exactly like gspread's get_all_records() output — this exercises everything
except the actual Google Sheets API call, which this sandbox has no network
path to reach. The API call itself (load_worksheet_rows) is a thin, isolated
wrapper specifically so this split is possible; it still needs a real test
against the real sheet, on a machine that can actually reach Google's API.
"""
from unittest.mock import patch

import pytest

from app.database import Base, engine, SessionLocal
from app.models.custom_exercise import CustomExercise
from app.models.user import User
from app.models.workout_log import Section, WorkoutLog
from migrations_data.migrate_from_sheets import (
    migrate_custom_exercises,
    migrate_users,
    migrate_workout_logs,
)


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_migrate_users_creates_accounts_with_forced_reset():
    db = SessionLocal()
    rows = [
        {"Username": "priyanshu", "Display_Name": "Priyanshu", "Email": "priyanshu@example.com"},
        {"Username": "friend1", "Display_Name": "Friend One", "Email": "friend1@example.com"},
    ]
    with patch("app.services.email.send_email"):
        mapping = migrate_users(rows, db, dry_run=False, send_email=True)
        db.commit()

    assert len(mapping) == 2
    user = db.query(User).filter(User.username == "priyanshu").first()
    assert user is not None
    assert user.must_reset_password is True
    assert user.email_verified is True
    db.close()


def test_migrate_users_skips_existing_accounts():
    db = SessionLocal()
    with patch("app.services.email.send_email"):
        migrate_users([{"Username": "existing", "Display_Name": "E", "Email": "e@example.com"}], db, dry_run=False, send_email=True)
        db.commit()

    # second run against the same username should skip, not duplicate
    with patch("app.services.email.send_email"):
        mapping = migrate_users([{"Username": "existing", "Display_Name": "E", "Email": "e@example.com"}], db, dry_run=False, send_email=True)
        db.commit()

    count = db.query(User).filter(User.username == "existing").count()
    assert count == 1
    assert "existing" in mapping
    db.close()


def test_migrate_users_dry_run_writes_nothing():
    db = SessionLocal()
    with patch("app.services.email.send_email"):
        migrate_users([{"Username": "shouldnotexist", "Display_Name": "X", "Email": "x@example.com"}], db, dry_run=True, send_email=False)
    db.rollback()

    assert db.query(User).filter(User.username == "shouldnotexist").count() == 0
    db.close()


def test_migrate_workout_logs_maps_fields_correctly():
    db = SessionLocal()
    with patch("app.services.email.send_email"):
        mapping = migrate_users([{"Username": "loguser", "Display_Name": "L", "Email": "l@example.com"}], db, dry_run=False, send_email=True)
        db.commit()

    rows = [{
        "User_ID": "loguser", "Date": "2026-08-29", "Day": "Saturday", "Section": "Main",
        "Exercise": "Barbell Back Squat", "Performed_As": "Hack Squat", "Muscle_Group": "Quads",
        "Set_Number": "1", "Weight_kg": "80", "Reps": "6",
    }]
    count = migrate_workout_logs(rows, db, mapping, dry_run=False)
    db.commit()

    assert count == 1
    log = db.query(WorkoutLog).first()
    assert log.exercise == "Barbell Back Squat"
    assert log.performed_as == "Hack Squat"
    assert float(log.weight_kg) == 80.0
    assert log.section == Section.main
    db.close()


def test_migrate_workout_logs_parses_warmup_metrics():
    db = SessionLocal()
    with patch("app.services.email.send_email"):
        mapping = migrate_users([{"Username": "warmupuser", "Display_Name": "W", "Email": "w@example.com"}], db, dry_run=False, send_email=True)
        db.commit()

    rows = [{
        "User_ID": "warmupuser", "Date": "2026-08-29", "Day": "Saturday", "Section": "Warmup",
        "Exercise": "Treadmill",
        "Field1_Label": "Inclination", "Field1_Value": "5",
        "Field2_Label": "Speed", "Field2_Value": "6",
        "Field3_Label": "", "Field3_Value": "",
    }]
    migrate_workout_logs(rows, db, mapping, dry_run=False)
    db.commit()

    log = db.query(WorkoutLog).first()
    assert log.metrics == {"Inclination": "5", "Speed": "6"}
    db.close()


def test_migrate_workout_logs_skips_unmapped_users():
    """A row referencing a username that wasn't migrated (e.g. typo'd or
    deleted account) must be skipped, not crash the whole migration."""
    db = SessionLocal()
    rows = [{"User_ID": "nonexistent", "Date": "2026-08-29", "Day": "Sat", "Section": "Main", "Exercise": "X"}]
    count = migrate_workout_logs(rows, db, {}, dry_run=False)
    assert count == 0
    db.close()


def test_migrate_custom_exercises_skips_inactive():
    db = SessionLocal()
    with patch("app.services.email.send_email"):
        mapping = migrate_users([{"Username": "exuser", "Display_Name": "E", "Email": "e2@example.com"}], db, dry_run=False, send_email=True)
        db.commit()

    rows = [
        {"User_ID": "exuser", "Main_Exercise": "Squat", "Custom_Alt_Name": "Hack Squat", "Active": "TRUE"},
        {"User_ID": "exuser", "Main_Exercise": "Bench", "Custom_Alt_Name": "Machine Press", "Active": "FALSE"},
    ]
    count = migrate_custom_exercises(rows, db, mapping, dry_run=False)
    db.commit()

    assert count == 1
    assert db.query(CustomExercise).count() == 1
    assert db.query(CustomExercise).first().custom_alt_name == "Hack Squat"
    db.close()
