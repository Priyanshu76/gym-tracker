"""
Progression engine — decides the next session's target weight/reps for an
exercise based on how the last session went. Deliberately built as pure
functions with no I/O: same pattern openGym itself uses for this exact kind
of training-science logic, and for the same reason — this is domain logic
where correctness matters and needs to be independently, thoroughly testable.

A note on Greyskull LP specifically: published descriptions of the program
vary on whether a single missed AMRAP triggers an immediate 10% reset, or
whether you get one retry at the same weight first. This implementation
defaults to "one retry, then reset" (the more commonly cited version) but
makes it a configurable parameter (`retries_before_reset`) rather than
asserting one exact canonical rule as definitively correct — worth knowing
if you've trained GSLP a specific way and want it to match exactly.
"""
from dataclasses import dataclass


@dataclass
class SetResult:
    reps: int
    weight_kg: float | None = None


@dataclass
class ProgressionOutcome:
    new_weight_kg: float | None
    new_reps_target: int
    new_consecutive_misses: int
    outcome: str  # "progressed", "repeated", "deloaded"
    note: str


def evaluate_linear(
    current_weight_kg: float,
    target_reps: int,
    sets_performed: list[SetResult],
    consecutive_misses: int,
    increment_kg: float = 2.5,
    deload_threshold: int = 3,
    deload_fraction: float = 0.10,
    is_bodyweight: bool = False,
) -> ProgressionOutcome:
    """Hit every set at the target reps -> add weight (or reps, if
    bodyweight). Miss -> repeat. Miss `deload_threshold` times in a row ->
    reduce load by `deload_fraction` and reset the miss counter."""
    hit = all(s.reps >= target_reps for s in sets_performed)

    if hit:
        if is_bodyweight:
            return ProgressionOutcome(
                new_weight_kg=None, new_reps_target=target_reps + 1, new_consecutive_misses=0,
                outcome="progressed", note=f"Hit every set — aim for {target_reps + 1} reps next time.",
            )
        new_weight = round(current_weight_kg + increment_kg, 2)
        return ProgressionOutcome(
            new_weight_kg=new_weight, new_reps_target=target_reps, new_consecutive_misses=0,
            outcome="progressed", note=f"Hit every set at {target_reps} reps — up to {new_weight}kg next time.",
        )

    new_misses = consecutive_misses + 1
    if new_misses >= deload_threshold:
        if is_bodyweight:
            new_target = max(1, target_reps - 2)
            return ProgressionOutcome(
                new_weight_kg=None, new_reps_target=new_target, new_consecutive_misses=0,
                outcome="deloaded", note=f"Missed {deload_threshold} sessions in a row — back to {new_target} reps to rebuild.",
            )
        new_weight = round(current_weight_kg * (1 - deload_fraction), 2)
        return ProgressionOutcome(
            new_weight_kg=new_weight, new_reps_target=target_reps, new_consecutive_misses=0,
            outcome="deloaded", note=f"Missed {deload_threshold} sessions in a row — deloading to {new_weight}kg.",
        )

    return ProgressionOutcome(
        new_weight_kg=None if is_bodyweight else current_weight_kg, new_reps_target=target_reps,
        new_consecutive_misses=new_misses, outcome="repeated",
        note=f"Missed target — try {target_reps} reps again next time.",
    )


def evaluate_greyskull_lp(
    current_weight_kg: float,
    target_reps: int,
    sets_performed: list[SetResult],
    consecutive_misses: int,
    increment_kg: float = 2.5,
    double_jump_multiplier: float = 2.0,
    retries_before_reset: int = 1,
    deload_fraction: float = 0.10,
) -> ProgressionOutcome:
    """Last set in `sets_performed` is the AMRAP set. Earlier sets must hit
    the fixed target reps for the session to count at all. AMRAP well above
    target (>= double_jump_multiplier x target) doubles the next increment.
    Missing resets after `retries_before_reset` consecutive misses, cutting
    load by `deload_fraction` — not a fixed miss count like plain linear,
    since GSLP is deliberately quicker to reset than a 5x5-style program."""
    if not sets_performed:
        raise ValueError("sets_performed must include at least the AMRAP set")

    straight_sets, amrap_set = sets_performed[:-1], sets_performed[-1]
    straight_sets_hit = all(s.reps >= target_reps for s in straight_sets)
    amrap_hit = amrap_set.reps >= target_reps

    if straight_sets_hit and amrap_hit:
        is_double = amrap_set.reps >= target_reps * double_jump_multiplier
        jump = increment_kg * 2 if is_double else increment_kg
        new_weight = round(current_weight_kg + jump, 2)
        note = (
            f"Doubled your AMRAP target ({amrap_set.reps} reps) — double jump to {new_weight}kg!"
            if is_double else f"Hit your AMRAP — up to {new_weight}kg next time."
        )
        return ProgressionOutcome(new_weight_kg=new_weight, new_reps_target=target_reps, new_consecutive_misses=0, outcome="progressed", note=note)

    new_misses = consecutive_misses + 1
    if new_misses > retries_before_reset:
        new_weight = round(current_weight_kg * (1 - deload_fraction), 2)
        return ProgressionOutcome(
            new_weight_kg=new_weight, new_reps_target=target_reps, new_consecutive_misses=0,
            outcome="deloaded", note=f"Missed again — 10% reset to {new_weight}kg.",
        )

    return ProgressionOutcome(
        new_weight_kg=current_weight_kg, new_reps_target=target_reps, new_consecutive_misses=new_misses,
        outcome="repeated", note=f"Missed your AMRAP target — same weight ({current_weight_kg}kg) again next time.",
    )


def evaluate_double_progression(
    current_weight_kg: float,
    rep_range_low: int,
    rep_range_high: int,
    current_reps_target: int,
    sets_performed: list[SetResult],
    increment_kg: float = 2.5,
) -> ProgressionOutcome:
    """Progress through the rep range at a fixed weight first; only once
    every set hits the TOP of the range does weight increase (and the rep
    target resets to the bottom of the range at the new weight)."""
    hit = all(s.reps >= current_reps_target for s in sets_performed)

    if not hit:
        return ProgressionOutcome(
            new_weight_kg=current_weight_kg, new_reps_target=current_reps_target, new_consecutive_misses=0,
            outcome="repeated", note=f"Didn't hit {current_reps_target} reps on every set — try again next time.",
        )

    if current_reps_target >= rep_range_high:
        new_weight = round(current_weight_kg + increment_kg, 2)
        return ProgressionOutcome(
            new_weight_kg=new_weight, new_reps_target=rep_range_low, new_consecutive_misses=0,
            outcome="progressed",
            note=f"Hit {rep_range_high} reps across every set — up to {new_weight}kg, back to {rep_range_low} reps.",
        )

    new_target = current_reps_target + 1
    return ProgressionOutcome(
        new_weight_kg=current_weight_kg, new_reps_target=new_target, new_consecutive_misses=0,
        outcome="progressed", note=f"Hit your target — aim for {new_target} reps next time at {current_weight_kg}kg.",
    )
