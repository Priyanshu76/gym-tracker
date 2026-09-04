from app.services.importers import detect_source, parse_fitnotes, parse_hevy, parse_strong


# ==================================================================
# Source detection
# ==================================================================
def test_detect_fitnotes():
    header = ["Date", "Exercise", "Category", "Weight (kg)", "Weight (lbs)", "Reps", "Distance", "Distance Unit", "Time", "Notes", "Kind"]
    assert detect_source(header) == "fitnotes"


def test_detect_strong():
    header = ["Date", "Workout Name", "Duration", "Exercise Name", "Set Order", "Weight", "Reps", "Distance", "Seconds", "Notes", "Workout Notes", "RPE"]
    assert detect_source(header) == "strong"


def test_detect_hevy():
    header = ["title", "start_time", "end_time", "description", "exercise_title", "superset_id", "exercise_notes", "set_index", "set_type", "weight_kg", "reps", "distance_km", "duration_seconds", "rpe"]
    assert detect_source(header) == "hevy"


def test_detect_unrecognized_format():
    assert detect_source(["foo", "bar", "baz"]) is None


# ==================================================================
# FitNotes
# ==================================================================
def test_parse_fitnotes_basic():
    rows = [
        {"Date": "2026-01-15", "Exercise": "Barbell Back Squat", "Category": "Legs", "Weight (kg)": "100", "Weight (lbs)": "", "Reps": "5", "Distance": "", "Distance Unit": "", "Time": "", "Notes": "", "Kind": ""},
    ]
    result = parse_fitnotes(rows)
    assert len(result) == 1
    assert result[0].workout_date.isoformat() == "2026-01-15"
    assert result[0].exercise_name == "Barbell Back Squat"
    assert result[0].weight_kg == 100.0
    assert result[0].reps == 5
    assert result[0].set_number == 1


def test_parse_fitnotes_infers_set_number_from_order():
    """No explicit set-order column — sets for the same exercise on the
    same day must be numbered in file order."""
    rows = [
        {"Date": "2026-01-15", "Exercise": "Bench Press", "Weight (kg)": "80", "Reps": "5"},
        {"Date": "2026-01-15", "Exercise": "Bench Press", "Weight (kg)": "80", "Reps": "5"},
        {"Date": "2026-01-15", "Exercise": "Bench Press", "Weight (kg)": "75", "Reps": "6"},
    ]
    result = parse_fitnotes(rows)
    assert [r.set_number for r in result] == [1, 2, 3]


def test_parse_fitnotes_converts_lbs_when_kg_missing():
    rows = [{"Date": "2026-01-15", "Exercise": "Deadlift", "Weight (kg)": "", "Weight (lbs)": "220", "Reps": "3"}]
    result = parse_fitnotes(rows)
    assert abs(result[0].weight_kg - 99.79) < 0.1  # 220 lbs ≈ 99.79 kg


def test_parse_fitnotes_skips_rows_with_bad_date():
    rows = [{"Date": "not-a-date", "Exercise": "Squat", "Weight (kg)": "100", "Reps": "5"}]
    assert parse_fitnotes(rows) == []


def test_parse_fitnotes_skips_rows_with_no_exercise_name():
    rows = [{"Date": "2026-01-15", "Exercise": "", "Weight (kg)": "100", "Reps": "5"}]
    assert parse_fitnotes(rows) == []


def test_parse_fitnotes_set_counters_reset_per_exercise():
    """Two different exercises on the same day must each start their own
    set numbering at 1, not share a running counter."""
    rows = [
        {"Date": "2026-01-15", "Exercise": "Squat", "Weight (kg)": "100", "Reps": "5"},
        {"Date": "2026-01-15", "Exercise": "Bench Press", "Weight (kg)": "80", "Reps": "5"},
        {"Date": "2026-01-15", "Exercise": "Squat", "Weight (kg)": "100", "Reps": "5"},
    ]
    result = parse_fitnotes(rows)
    squat_sets = [r.set_number for r in result if r.exercise_name == "Squat"]
    bench_sets = [r.set_number for r in result if r.exercise_name == "Bench Press"]
    assert squat_sets == [1, 2]
    assert bench_sets == [1]


# ==================================================================
# Strong
# ==================================================================
def test_parse_strong_basic():
    rows = [
        {"Date": "2020-12-30 18:51:52", "Workout Name": "Evening Workout", "Duration": "2h 38m",
         "Exercise Name": "Clean (Barbell)", "Set Order": "3", "Weight": "70.0", "Reps": "2",
         "Distance": "0", "Seconds": "0", "Notes": "", "Workout Notes": "", "RPE": "8"},
    ]
    result = parse_strong(rows)
    assert len(result) == 1
    assert result[0].workout_date.isoformat() == "2020-12-30"
    assert result[0].exercise_name == "Clean (Barbell)"
    assert result[0].set_number == 3
    assert result[0].weight_kg == 70.0
    assert result[0].rpe == 8.0


def test_parse_strong_set_order_taken_directly_not_inferred():
    """Unlike FitNotes, Strong provides an explicit Set Order column that
    should be used as-is."""
    rows = [
        {"Date": "2020-12-30 18:51:52", "Exercise Name": "Squat", "Set Order": "5", "Weight": "100", "Reps": "5"},
    ]
    assert parse_strong(rows)[0].set_number == 5


def test_parse_strong_skips_bad_date():
    rows = [{"Date": "garbage", "Exercise Name": "Squat", "Set Order": "1", "Weight": "100", "Reps": "5"}]
    assert parse_strong(rows) == []


def test_parse_strong_seconds_maps_to_duration():
    rows = [{"Date": "2020-12-30 18:51:52", "Exercise Name": "Plank", "Set Order": "1", "Seconds": "60"}]
    result = parse_strong(rows)
    assert result[0].duration_seconds == 60


# ==================================================================
# Hevy
# ==================================================================
def test_parse_hevy_basic():
    rows = [
        {"title": "Morning workout", "start_time": "22 Dec 2025, 08:00", "end_time": "22 Dec 2025, 08:37",
         "exercise_title": "Leg Press (Machine)", "set_index": "1", "set_type": "normal",
         "weight_kg": "90", "reps": "12", "duration_seconds": "0", "rpe": "7.5"},
    ]
    result = parse_hevy(rows)
    assert len(result) == 1
    assert result[0].workout_date.isoformat() == "2025-12-22"
    assert result[0].exercise_name == "Leg Press (Machine)"
    assert result[0].set_number == 2  # set_index 1 -> our set_number 2 (0-based to 1-based)
    assert result[0].weight_kg == 90.0
    assert result[0].set_type == "working"


def test_parse_hevy_set_index_is_zero_based_shifted_to_one_based():
    rows = [{"start_time": "22 Dec 2025, 08:00", "exercise_title": "Squat", "set_index": "0"}]
    assert parse_hevy(rows)[0].set_number == 1


def test_parse_hevy_maps_set_types_correctly():
    rows = [
        {"start_time": "22 Dec 2025, 08:00", "exercise_title": "Squat", "set_index": "0", "set_type": "warmup"},
        {"start_time": "22 Dec 2025, 08:00", "exercise_title": "Squat", "set_index": "1", "set_type": "dropset"},
        {"start_time": "22 Dec 2025, 08:00", "exercise_title": "Squat", "set_index": "2", "set_type": "failure"},
        {"start_time": "22 Dec 2025, 08:00", "exercise_title": "Squat", "set_index": "3", "set_type": "normal"},
    ]
    result = parse_hevy(rows)
    assert [r.set_type for r in result] == ["warmup", "drop_set", "failure", "working"]


def test_parse_hevy_weight_already_in_kg_no_conversion():
    rows = [{"start_time": "22 Dec 2025, 08:00", "exercise_title": "Pull Up (Assisted)", "set_index": "0", "weight_kg": "21"}]
    assert parse_hevy(rows)[0].weight_kg == 21.0


def test_parse_hevy_skips_bad_date():
    rows = [{"start_time": "not a date", "exercise_title": "Squat", "set_index": "0"}]
    assert parse_hevy(rows) == []


def test_parse_hevy_bodyweight_zero_weight_is_preserved_not_treated_as_missing():
    """Weight 0 for an assisted/bodyweight exercise is meaningful data, not
    a missing value — must not be silently converted to None."""
    rows = [{"start_time": "22 Dec 2025, 08:00", "exercise_title": "Push-Up", "set_index": "0", "weight_kg": "0", "reps": "20"}]
    result = parse_hevy(rows)
    assert result[0].weight_kg == 0.0
    assert result[0].weight_kg is not None
