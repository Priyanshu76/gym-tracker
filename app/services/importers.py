"""
Importers for workout history exported from other trackers. Each app's
column format was confirmed against real sample exports (not guessed) —
see the format notes on each parser.

Deliberately built as pure functions operating on already-parsed CSV rows
(list[dict]), same pattern as the progression engine — the actual file
upload/CSV-reading is a thin wrapper in the router, kept separate so this
logic is fully testable without needing to construct real file uploads.
"""
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class ImportedSet:
    workout_date: date
    exercise_name: str
    set_number: int
    weight_kg: float | None = None
    reps: int | None = None
    duration_seconds: int | None = None
    rpe: float | None = None
    set_type: str = "working"
    notes: str | None = None


LBS_TO_KG = 0.45359237


def detect_source(header: list[str]) -> str | None:
    """Each format's column set is distinct enough that checking for one or
    two unique column names reliably identifies it — no need for anything
    fuzzier than an exact membership check."""
    header_set = set(header)
    if "Kind" in header_set and "Weight (kg)" in header_set:
        return "fitnotes"
    if "Set Order" in header_set and "Workout Name" in header_set:
        return "strong"
    if "exercise_title" in header_set and "set_index" in header_set:
        return "hevy"
    return None


def _to_float_or_none(value: str) -> float | None:
    value = (value or "").strip()
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_int_or_none(value: str) -> int | None:
    f = _to_float_or_none(value)
    return int(f) if f is not None else None


def _normalize_set_type(raw: str) -> str:
    raw = (raw or "").strip().lower().replace(" ", "").replace("-", "")
    mapping = {
        "warmup": "warmup", "warmupset": "warmup",
        "dropset": "drop_set", "drop": "drop_set",
        "failure": "failure", "amrap": "amrap",
        "normal": "working", "working": "working", "workingset": "working",
    }
    return mapping.get(raw, "working")


def parse_fitnotes(rows: list[dict]) -> list[ImportedSet]:
    """
    Columns (confirmed from FitNotes' own migration documentation):
    Date, Exercise, Category, Weight (kg), Weight (lbs), Reps, Distance,
    Distance Unit, Time, Notes, Kind
    Date format: YYYY-mm-dd. No explicit set-order column — sets are
    inferred to be in performed order per (date, exercise) as they appear
    in the file, which matches how the app writes the export.
    """
    results = []
    set_counters: dict[tuple, int] = {}
    for row in rows:
        try:
            workout_date = date.fromisoformat(row.get("Date", "").strip())
        except ValueError:
            continue  # unparseable date — skip rather than fail the whole import
        exercise_name = (row.get("Exercise") or "").strip()
        if not exercise_name:
            continue

        weight_kg = _to_float_or_none(row.get("Weight (kg)", ""))
        if weight_kg is None:
            weight_lbs = _to_float_or_none(row.get("Weight (lbs)", ""))
            if weight_lbs is not None:
                weight_kg = round(weight_lbs * LBS_TO_KG, 2)

        key = (workout_date, exercise_name)
        set_counters[key] = set_counters.get(key, 0) + 1

        results.append(ImportedSet(
            workout_date=workout_date, exercise_name=exercise_name, set_number=set_counters[key],
            weight_kg=weight_kg, reps=_to_int_or_none(row.get("Reps", "")),
            set_type=_normalize_set_type(row.get("Kind", "")),
            notes=(row.get("Notes") or "").strip() or None,
        ))
    return results


def parse_strong(rows: list[dict]) -> list[ImportedSet]:
    """
    Columns (confirmed from a real Strong export sample):
    Date, Workout Name, Duration, Exercise Name, Set Order, Weight, Reps,
    Distance, Seconds, Notes, Workout Notes, RPE
    Date format: 'YYYY-MM-DD HH:MM:SS'.

    Known limitation: the Weight column has no unit in its name — Strong
    lets users set kg or lb globally in the app, and the export doesn't
    carry that setting. This assumes kg, matching this app's own internal
    unit; a lb-configured export will import with incorrect magnitudes.
    """
    results = []
    for row in rows:
        raw_date = (row.get("Date") or "").strip()
        try:
            workout_date = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S").date()
        except ValueError:
            continue
        exercise_name = (row.get("Exercise Name") or "").strip()
        if not exercise_name:
            continue

        results.append(ImportedSet(
            workout_date=workout_date, exercise_name=exercise_name,
            set_number=_to_int_or_none(row.get("Set Order", "")) or 1,
            weight_kg=_to_float_or_none(row.get("Weight", "")),
            reps=_to_int_or_none(row.get("Reps", "")),
            duration_seconds=_to_int_or_none(row.get("Seconds", "")),
            rpe=_to_float_or_none(row.get("RPE", "")),
            notes=(row.get("Notes") or "").strip() or None,
        ))
    return results


def parse_hevy(rows: list[dict]) -> list[ImportedSet]:
    """
    Columns (confirmed from a real Hevy export sample):
    title, start_time, end_time, description, exercise_title, superset_id,
    exercise_notes, set_index, set_type, weight_kg, reps, distance_km,
    duration_seconds, rpe
    Date format: 'DD Mon YYYY, HH:MM'. set_index is 0-based in the source
    file; this app's set numbering starts at 1, so it's shifted by one.
    Already in kg — no unit ambiguity, unlike Strong.
    """
    results = []
    for row in rows:
        raw_date = (row.get("start_time") or "").strip()
        try:
            workout_date = datetime.strptime(raw_date, "%d %b %Y, %H:%M").date()
        except ValueError:
            continue
        exercise_name = (row.get("exercise_title") or "").strip()
        if not exercise_name:
            continue

        set_index = _to_int_or_none(row.get("set_index", ""))
        results.append(ImportedSet(
            workout_date=workout_date, exercise_name=exercise_name,
            set_number=(set_index + 1) if set_index is not None else 1,
            weight_kg=_to_float_or_none(row.get("weight_kg", "")),
            reps=_to_int_or_none(row.get("reps", "")),
            duration_seconds=_to_int_or_none(row.get("duration_seconds", "")),
            rpe=_to_float_or_none(row.get("rpe", "")),
            set_type=_normalize_set_type(row.get("set_type", "")),
            notes=(row.get("exercise_notes") or "").strip() or None,
        ))
    return results


PARSERS = {"fitnotes": parse_fitnotes, "strong": parse_strong, "hevy": parse_hevy}
