import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.main import app
from migrations_data.seed_exercises import seed


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield


def _logged_in_client(username: str) -> TestClient:
    client = TestClient(app)
    with patch("app.services.email.send_email"):
        from app.models.pending_signup import PendingSignup
        from app.models.user import User
        from app.services.security import hash_password
        client.post("/api/signup", json={"username": username, "display_name": username.title(), "email": f"{username}@example.com", "website_url": ""})
        db = SessionLocal()
        pending = db.query(PendingSignup).filter(PendingSignup.username == username).first()
        client.get(f"/api/verify-email?request_id={pending.id}&token={pending.verification_token}")
        db.refresh(pending)
        client.get(f"/api/approve-signup?request_id={pending.id}&token={pending.approval_token}")
        user = db.query(User).filter(User.username == username).first()
        user.password_hash = hash_password("KnownPass123!")
        db.commit()
        db.close()
    client.post("/api/login", json={"username": username, "password": "KnownPass123!"})
    return client


def _upload_csv(client, content: str, filename="export.csv"):
    return client.post(
        "/api/export/workout-history/import",
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")},
    )


def test_import_fitnotes_csv():
    client = _logged_in_client("importfituser")
    csv_content = (
        "Date,Exercise,Category,Weight (kg),Weight (lbs),Reps,Distance,Distance Unit,Time,Notes,Kind\n"
        "2026-01-15,Barbell Back Squat,Legs,100,,5,,,,,\n"
        "2026-01-15,Barbell Back Squat,Legs,100,,5,,,,,\n"
    )
    r = _upload_csv(client, csv_content)
    assert r.status_code == 200, r.text
    assert r.json()["detected_source"] == "fitnotes"
    assert r.json()["imported_count"] == 2

    logs = client.get("/api/workout-logs").json()
    assert len(logs) == 2
    assert logs[0]["exercise"] == "Barbell Back Squat"
    assert logs[0]["set_number"] == 1
    assert logs[1]["set_number"] == 2


def test_import_strong_csv():
    client = _logged_in_client("importstronguser")
    csv_content = (
        "Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE\n"
        '2020-12-30 18:51:52,"Evening Workout",2h 38m,"Clean (Barbell)",3,70.0,2,0,0,,,\n'
    )
    r = _upload_csv(client, csv_content)
    assert r.status_code == 200, r.text
    assert r.json()["detected_source"] == "strong"
    assert r.json()["imported_count"] == 1

    logs = client.get("/api/workout-logs").json()
    assert logs[0]["exercise"] == "Clean (Barbell)"
    assert logs[0]["weight_kg"] == 70.0
    assert logs[0]["day_name"] == "Wednesday"  # 2020-12-30 was a Wednesday


def test_import_hevy_csv():
    client = _logged_in_client("importhevyuser")
    csv_content = (
        'title,start_time,end_time,description,exercise_title,superset_id,exercise_notes,set_index,set_type,weight_kg,reps,distance_km,duration_seconds,rpe\n'
        '"Morning workout","22 Dec 2025, 08:00","22 Dec 2025, 08:37",,"Leg Press (Machine)",,,1,normal,90,12,,0,7.5\n'
    )
    r = _upload_csv(client, csv_content)
    assert r.status_code == 200, r.text
    assert r.json()["detected_source"] == "hevy"

    logs = client.get("/api/workout-logs").json()
    assert logs[0]["exercise"] == "Leg Press (Machine)"
    assert logs[0]["set_number"] == 2
    assert logs[0]["rpe"] == 7.5


def test_import_enriches_muscle_group_from_library_when_name_matches():
    client = _logged_in_client("importenrichuser")
    csv_content = (
        "Date,Exercise,Weight (kg),Weight (lbs),Reps,Kind\n"
        "2026-01-15,Barbell Back Squat,100,,5,\n"
    )
    r = _upload_csv(client, csv_content)
    assert r.status_code == 200, r.text
    logs = client.get("/api/workout-logs").json()
    assert len(logs) == 1
    assert logs[0]["muscle_group"] == "Quads + Glutes"  # matches our seeded library exactly


def test_import_unrecognized_format_returns_400():
    client = _logged_in_client("importbaduser")
    r = _upload_csv(client, "foo,bar,baz\n1,2,3\n")
    assert r.status_code == 400
    assert "Unrecognized" in r.json()["detail"]


def test_import_empty_csv_returns_400():
    client = _logged_in_client("importemptyuser")
    r = _upload_csv(client, "")
    assert r.status_code == 400


def test_import_no_valid_rows_succeeds_with_zero_count():
    client = _logged_in_client("importnovaliduser")
    csv_content = "Date,Exercise,Weight (kg),Reps,Kind\nnot-a-date,Squat,100,5,\n"
    r = _upload_csv(client, csv_content)
    assert r.status_code == 200
    assert r.json()["imported_count"] == 0


def test_import_scoped_to_current_user():
    alice = _logged_in_client("importisoalice")
    bob = _logged_in_client("importisobob")
    csv_content = "Date,Exercise,Weight (kg),Reps,Kind\n2026-01-15,Squat,100,5,\n"
    _upload_csv(alice, csv_content)

    assert len(alice.get("/api/workout-logs").json()) == 1
    assert len(bob.get("/api/workout-logs").json()) == 0


def test_import_requires_authentication():
    anon = TestClient(app)
    r = anon.post(
        "/api/export/workout-history/import",
        files={"file": ("x.csv", io.BytesIO(b"a,b,c\n1,2,3\n"), "text/csv")},
    )
    assert r.status_code == 401
