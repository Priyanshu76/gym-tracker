"""
One-off migration: pulls existing data out of the old Google Sheets
(Users, Workout_Log, Custom_Exercises) and writes it into Postgres.

Sessions and Pending_Signups are intentionally NOT migrated:
- Sessions: everyone needs to log in fresh regardless (see password note below),
  so old session tokens are moot.
- Pending_Signups: any old unresolved signup requests are stale by definition
  once this migration runs — anyone who still wants an account should just
  sign up again through the new system.

IMPORTANT — password handling: the old system hashed passwords with scrypt
(via Node's crypto module in n8n); the new system uses argon2 via passlib.
These are not compatible, and there is no reasonable way to migrate a hash
across algorithms without the plaintext password. Every migrated user is
therefore given a fresh random temp password and must_reset_password=True,
identical to how a brand-new approved signup works. This is a deliberate
simplification, not an oversight — reimplementing scrypt verification just
for a one-time migration isn't worth the complexity or the security review
it would deserve.

Usage:
    python -m migrations_data.migrate_from_sheets --sheet-id YOUR_SHEET_ID \\
        --service-account-file path/to/service-account.json [--dry-run] [--no-email]

Requires: pip install gspread google-auth (not added to the main app's
requirements.txt since this script never runs as part of the app itself).
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models.custom_exercise import CustomExercise  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.workout_log import Section, WorkoutLog  # noqa: E402
from app.services import email as email_service  # noqa: E402
from app.services.security import generate_temp_password, hash_password  # noqa: E402


def load_worksheet_rows(sheet_id: str, service_account_file: str, tab_name: str) -> list[dict]:
    """Returns a list of dicts, one per row, keyed by the sheet's header row.
    Isolated into its own function so the transformation logic below can be
    unit-tested against plain Python dicts without ever calling Google's API.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.worksheet(tab_name)
    return worksheet.get_all_records()


def migrate_users(rows: list[dict], db, dry_run: bool, send_email: bool) -> dict[str, str]:
    """Returns a mapping of old Username -> new Postgres User.id (str), used
    by the workout-logs and custom-exercises migration steps below to
    resolve the right owner for each row."""
    username_to_new_id: dict[str, str] = {}

    for row in rows:
        username = str(row.get("Username", "")).strip()
        if not username:
            continue

        existing = db.query(User).filter(User.username == username).first()
        if existing:
            username_to_new_id[username] = str(existing.id)
            print(f"  [skip] {username} already exists in Postgres")
            continue

        temp_password = generate_temp_password()
        display_name = str(row.get("Display_Name") or username)
        email_addr = str(row.get("Email") or f"{username}@unknown.invalid")

        print(f"  [{'DRY RUN — would create' if dry_run else 'creating'}] {username} <{email_addr}>")

        if dry_run:
            continue

        user = User(
            username=username,
            display_name=display_name,
            email=email_addr,
            email_verified=True,
            password_hash=hash_password(temp_password),
            must_reset_password=True,
        )
        db.add(user)
        db.flush()  # get user.id without committing yet
        username_to_new_id[username] = str(user.id)

        if send_email and "@" in email_addr and not email_addr.endswith("@unknown.invalid"):
            try:
                email_service.send_welcome_email(
                    to=email_addr, display_name=display_name, username=username, temp_password=temp_password
                )
            except Exception as e:  # noqa: BLE001 — a failed email must never abort the migration
                print(f"    (warning: could not email {username}: {e})")
        else:
            print(f"    temp password for {username}: {temp_password}  <-- save this, it won't be shown again")

    return username_to_new_id


def _parse_metrics(row: dict) -> dict | None:
    metrics = {}
    for i in (1, 2, 3):
        label = str(row.get(f"Field{i}_Label", "")).strip()
        value = str(row.get(f"Field{i}_Value", "")).strip()
        if label and value:
            metrics[label] = value
    return metrics or None


def migrate_workout_logs(rows: list[dict], db, username_to_new_id: dict[str, str], dry_run: bool) -> int:
    count = 0
    for row in rows:
        username = str(row.get("User_ID", "")).strip()  # old sheet stored a username-ish string here in practice
        # Fall back: some deployments stored the actual username directly in User_ID.
        new_user_id = username_to_new_id.get(username)
        if not new_user_id:
            continue

        section_raw = str(row.get("Section") or "Main")
        try:
            section = Section(section_raw)
        except ValueError:
            section = Section.main

        if dry_run:
            count += 1
            continue

        log = WorkoutLog(
            user_id=new_user_id,
            workout_date=row.get("Date"),
            day_name=str(row.get("Day", "")),
            section=section,
            exercise=str(row.get("Exercise", "")),
            performed_as=str(row.get("Performed_As") or "") or None,
            muscle_group=str(row.get("Muscle_Group") or "") or None,
            set_number=int(row["Set_Number"]) if row.get("Set_Number") else None,
            weight_kg=float(row["Weight_kg"]) if row.get("Weight_kg") else None,
            reps=int(row["Reps"]) if row.get("Reps") else None,
            metrics=_parse_metrics(row),
        )
        db.add(log)
        count += 1
    return count


def migrate_custom_exercises(rows: list[dict], db, username_to_new_id: dict[str, str], dry_run: bool) -> int:
    count = 0
    for row in rows:
        if str(row.get("Active", "TRUE")).upper() == "FALSE":
            continue
        username = str(row.get("User_ID", "")).strip()
        new_user_id = username_to_new_id.get(username)
        if not new_user_id:
            continue

        if dry_run:
            count += 1
            continue

        exercise = CustomExercise(
            user_id=new_user_id,
            main_exercise=str(row.get("Main_Exercise", "")),
            custom_alt_name=str(row.get("Custom_Alt_Name", "")),
        )
        db.add(exercise)
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID (from its URL)")
    parser.add_argument("--service-account-file", required=True, help="Path to a Google service account JSON key")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be migrated without writing anything")
    parser.add_argument("--no-email", action="store_true", help="Print temp passwords to console instead of emailing them")
    args = parser.parse_args()

    print("=== Loading data from Google Sheets ===")
    users_rows = load_worksheet_rows(args.sheet_id, args.service_account_file, "Users")
    workout_rows = load_worksheet_rows(args.sheet_id, args.service_account_file, "Workout_Log")
    exercise_rows = load_worksheet_rows(args.sheet_id, args.service_account_file, "Custom_Exercises")
    print(f"Users: {len(users_rows)}, Workout_Log: {len(workout_rows)}, Custom_Exercises: {len(exercise_rows)}")

    db = SessionLocal()
    try:
        print("\n=== Migrating users ===")
        username_map = migrate_users(users_rows, db, args.dry_run, send_email=not args.no_email)

        print("\n=== Migrating workout logs ===")
        log_count = migrate_workout_logs(workout_rows, db, username_map, args.dry_run)
        print(f"  {'would migrate' if args.dry_run else 'migrated'} {log_count} workout log rows")

        print("\n=== Migrating custom exercises ===")
        ex_count = migrate_custom_exercises(exercise_rows, db, username_map, args.dry_run)
        print(f"  {'would migrate' if args.dry_run else 'migrated'} {ex_count} custom exercise rows")

        if args.dry_run:
            print("\nDRY RUN — nothing was written. Re-run without --dry-run to apply.")
            db.rollback()
        else:
            db.commit()
            print("\nDone. Committed to Postgres.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
