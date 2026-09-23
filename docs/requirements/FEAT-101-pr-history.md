# FEAT-101 — PR history per exercise

**Type:** Feature · **Depends on:** REFACTOR-100 · **Area:** backend + dashboard
**Roadmap:** FUTURE_ROADMAP.md §5 (PR history) and §7 (set-type-aware PRs)

## User story

> As a lifter, I want to see how my personal record on an exercise has
> improved over time, not just today's best, so I can tell whether I'm
> still progressing.

Today the dashboard's "Personal records" cards show only the single
all-time best per exercise. Users can't see how they got there or by how
much they beat their previous best.

## Scope

### Part A — API (required)

`GET /api/workout-logs/pr-history?exercise=<exercise name>`

Returns the chronological list of **PR events** for the logged-in user on
that exercise. A PR event is a set that beat every earlier set for that
exercise.

Each entry:

| Field            | Type            | Notes                                                    |
|------------------|-----------------|----------------------------------------------------------|
| `workout_date`   | date            |                                                          |
| `weight_kg`      | number          |                                                          |
| `reps`           | integer         |                                                          |
| `estimated_1rm`  | number          | Epley, rounded to 1 decimal                              |
| `pr_type`        | string          | `"baseline"`, `"weight"`, or `"estimated_1rm"`           |
| `improvement_kg` | number \| null  | How much it beat the previous best on the same metric: the weight for a weight PR, the est. 1RM for an est.-1RM PR. Rounded to 1 decimal. `null` for the baseline. |

### Part B — Dashboard (stretch)

On each Personal-records card, add one line under the date:
**"▲ +X kg vs previous PR"**, or **"First PR"** when there's only a baseline.

## Business rules

1. **Same definition as the live PR badge.** Use the same rules as the badge
   shown when logging a set (see REFACTOR-100). There must be one PR
   definition in the codebase, not two.
2. Only **Main** section sets count, and only **working** sets. Warm-up,
   drop sets, etc. never count, even if they're heavier.
3. Sets without a weight (e.g. bodyweight push-ups) or without reps are
   ignored.
4. The first qualifying set is the **baseline** (`pr_type: "baseline"`).
5. Later sets appear only if they beat the running best: first by weight,
   then by estimated 1RM. Sets that don't beat it are omitted.
6. **Order is by workout date**, oldest first. Several sets on the same day
   are ordered by set number. Users import years of history from FitNotes,
   Strong and Hevy in one go, and the history must still be in true
   workout-date order.
7. **Ownership.** Users only ever see their own data. No auth → `401`.
8. Unknown exercise or no qualifying sets → `200` with an empty list. This
   matches `GET /api/workout-logs/last`.

## Test scenarios

| ID    | Given                                                                   | Expect                                                                      |
|-------|-------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| TS-1  | No sets logged                                                          | `[]`                                                                        |
| TS-2  | Squat 100×5 (Sep 1), 105×5 (Sep 3), 105×8 (Sep 5), 110×5 (Sep 8)        | 4 entries: baseline, weight (+5.0), estimated_1rm, weight (+5.0)            |
| TS-3  | Squat 100×5, then 90×5, then 102.5×5                                    | 2 entries: baseline, weight (+2.5). The 90 kg set is omitted.               |
| TS-4  | A 200 kg `warmup` set and a 180 kg `drop_set`, plus a 100 kg working set | Only the 100 kg working set appears (baseline)                              |
| TS-5  | Push-Up with reps only, no weight                                        | `[]`                                                                        |
| TS-6  | Log the Sep 10 session (110×5) *first*, then the Sep 1 session (100×5)   | Sep 1 is the baseline and Sep 10 is a weight PR (+10.0), in date order      |
| TS-7  | Sets in the `Warmup` section for the same exercise name                  | Ignored                                                                     |
| TS-8  | Alice has squat history; Bob requests squat history                     | Bob gets `[]`                                                               |
| TS-9  | No login                                                                | `401`                                                                       |

## Open questions (resolve before building)

1. The live PR badge matches on the `exercise` field. The dashboard's PR
   cards group by `performed_as` when an exercise was substituted. Which
   should PR history use?
2. Should `amrap` / `failure` sets count as PR-eligible, or only `working`?
3. Is one exercise per request enough for now, or does the dashboard need
   all exercises in one call?
