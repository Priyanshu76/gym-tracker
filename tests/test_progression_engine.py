import pytest

from app.services.progression import (
    SetResult,
    evaluate_double_progression,
    evaluate_greyskull_lp,
    evaluate_linear,
)


# ==================================================================
# Linear progression
# ==================================================================
def test_linear_progresses_when_all_sets_hit_target():
    result = evaluate_linear(
        current_weight_kg=100, target_reps=5,
        sets_performed=[SetResult(5), SetResult(5), SetResult(5)],
        consecutive_misses=0, increment_kg=2.5,
    )
    assert result.outcome == "progressed"
    assert result.new_weight_kg == 102.5
    assert result.new_consecutive_misses == 0


def test_linear_progresses_when_sets_exceed_target():
    """Exceeding the target should still count as a hit, not a special case."""
    result = evaluate_linear(
        current_weight_kg=100, target_reps=5,
        sets_performed=[SetResult(6), SetResult(7), SetResult(5)],
        consecutive_misses=0,
    )
    assert result.outcome == "progressed"


def test_linear_repeats_on_single_missed_set():
    result = evaluate_linear(
        current_weight_kg=100, target_reps=5,
        sets_performed=[SetResult(5), SetResult(5), SetResult(4)],  # last set missed
        consecutive_misses=0,
    )
    assert result.outcome == "repeated"
    assert result.new_weight_kg == 100
    assert result.new_consecutive_misses == 1


def test_linear_never_advances_load_on_a_miss():
    """Core invariant explicitly called out in the platform analysis and
    openGym's own description: missed reps must never advance the load."""
    result = evaluate_linear(
        current_weight_kg=100, target_reps=5,
        sets_performed=[SetResult(3)],
        consecutive_misses=0,
    )
    assert result.new_weight_kg <= 100


def test_linear_deloads_after_threshold_consecutive_misses():
    result = evaluate_linear(
        current_weight_kg=100, target_reps=5,
        sets_performed=[SetResult(3)],
        consecutive_misses=2,  # this miss will be the 3rd
        deload_threshold=3, deload_fraction=0.10,
    )
    assert result.outcome == "deloaded"
    assert result.new_weight_kg == 90.0
    assert result.new_consecutive_misses == 0


def test_linear_does_not_deload_before_threshold():
    result = evaluate_linear(
        current_weight_kg=100, target_reps=5,
        sets_performed=[SetResult(3)],
        consecutive_misses=1,  # this miss will be the 2nd, threshold is 3
        deload_threshold=3,
    )
    assert result.outcome == "repeated"
    assert result.new_weight_kg == 100


def test_linear_bodyweight_progresses_reps_not_weight():
    result = evaluate_linear(
        current_weight_kg=0, target_reps=10,
        sets_performed=[SetResult(10), SetResult(10)],
        consecutive_misses=0, is_bodyweight=True,
    )
    assert result.outcome == "progressed"
    assert result.new_weight_kg is None
    assert result.new_reps_target == 11


def test_linear_bodyweight_deload_reduces_reps_not_weight():
    result = evaluate_linear(
        current_weight_kg=0, target_reps=10,
        sets_performed=[SetResult(5)],
        consecutive_misses=2, deload_threshold=3, is_bodyweight=True,
    )
    assert result.outcome == "deloaded"
    assert result.new_weight_kg is None
    assert result.new_reps_target == 8


# ==================================================================
# Greyskull LP
# ==================================================================
def test_greyskull_progresses_on_amrap_hit():
    result = evaluate_greyskull_lp(
        current_weight_kg=60, target_reps=5,
        sets_performed=[SetResult(5), SetResult(5), SetResult(5)],  # last is AMRAP, exactly hit
        consecutive_misses=0,
    )
    assert result.outcome == "progressed"
    assert result.new_weight_kg == 62.5


def test_greyskull_double_jump_on_amrap_far_exceeding_target():
    result = evaluate_greyskull_lp(
        current_weight_kg=60, target_reps=5,
        sets_performed=[SetResult(5), SetResult(5), SetResult(10)],  # AMRAP = 2x target
        consecutive_misses=0, increment_kg=2.5, double_jump_multiplier=2.0,
    )
    assert result.outcome == "progressed"
    assert result.new_weight_kg == 65.0  # 60 + (2.5 * 2)


def test_greyskull_no_double_jump_just_below_multiplier():
    result = evaluate_greyskull_lp(
        current_weight_kg=60, target_reps=5,
        sets_performed=[SetResult(5), SetResult(5), SetResult(9)],  # just under 2x
        consecutive_misses=0, increment_kg=2.5, double_jump_multiplier=2.0,
    )
    assert result.new_weight_kg == 62.5  # single increment only


def test_greyskull_fails_if_straight_sets_missed_even_with_good_amrap():
    """The fixed-rep sets must ALSO be hit — a great AMRAP doesn't rescue a
    missed straight set."""
    result = evaluate_greyskull_lp(
        current_weight_kg=60, target_reps=5,
        sets_performed=[SetResult(3), SetResult(5), SetResult(8)],  # first set missed
        consecutive_misses=0,
    )
    assert result.outcome != "progressed"


def test_greyskull_first_miss_retries_same_weight():
    result = evaluate_greyskull_lp(
        current_weight_kg=60, target_reps=5,
        sets_performed=[SetResult(5), SetResult(5), SetResult(3)],
        consecutive_misses=0, retries_before_reset=1,
    )
    assert result.outcome == "repeated"
    assert result.new_weight_kg == 60
    assert result.new_consecutive_misses == 1


def test_greyskull_second_consecutive_miss_triggers_10_percent_reset():
    result = evaluate_greyskull_lp(
        current_weight_kg=60, target_reps=5,
        sets_performed=[SetResult(5), SetResult(5), SetResult(3)],
        consecutive_misses=1, retries_before_reset=1,
    )
    assert result.outcome == "deloaded"
    assert result.new_weight_kg == 54.0
    assert result.new_consecutive_misses == 0


def test_greyskull_requires_at_least_one_set():
    with pytest.raises(ValueError):
        evaluate_greyskull_lp(current_weight_kg=60, target_reps=5, sets_performed=[], consecutive_misses=0)


# ==================================================================
# Double progression
# ==================================================================
def test_double_progression_advances_reps_within_range():
    result = evaluate_double_progression(
        current_weight_kg=20, rep_range_low=8, rep_range_high=12, current_reps_target=8,
        sets_performed=[SetResult(8), SetResult(8), SetResult(8)],
    )
    assert result.outcome == "progressed"
    assert result.new_weight_kg == 20  # weight unchanged — still climbing the rep range
    assert result.new_reps_target == 9


def test_double_progression_increases_weight_at_top_of_range():
    result = evaluate_double_progression(
        current_weight_kg=20, rep_range_low=8, rep_range_high=12, current_reps_target=12,
        sets_performed=[SetResult(12), SetResult(12), SetResult(12)],
    )
    assert result.outcome == "progressed"
    assert result.new_weight_kg == 22.5
    assert result.new_reps_target == 8  # resets to the bottom of the range at the new weight


def test_double_progression_repeats_on_missed_reps():
    result = evaluate_double_progression(
        current_weight_kg=20, rep_range_low=8, rep_range_high=12, current_reps_target=10,
        sets_performed=[SetResult(10), SetResult(9), SetResult(10)],  # one set missed
    )
    assert result.outcome == "repeated"
    assert result.new_weight_kg == 20
    assert result.new_reps_target == 10  # unchanged, no regression


def test_double_progression_never_skips_past_the_top_of_the_range():
    """Even a huge overperformance shouldn't jump the reps target above
    rep_range_high in one step — it should trigger the weight increase
    instead, per test_double_progression_increases_weight_at_top_of_range."""
    result = evaluate_double_progression(
        current_weight_kg=20, rep_range_low=8, rep_range_high=12, current_reps_target=11,
        sets_performed=[SetResult(20), SetResult(20), SetResult(20)],  # wildly exceeds range
    )
    assert result.new_reps_target <= 12
