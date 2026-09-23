# REFACTOR-100 — Extract PR detection into a reusable service

**Type:** Refactor (no behavior change) · **Blocks:** FEAT-101 · **Area:** backend

## Problem

Personal-record (PR) detection lives as two private helpers inside the
workouts router (`app/routers/workouts.py`):

- `_estimated_1rm(weight_kg, reps)` — Epley formula
- `_check_pr(db, user_id, exercise, weight_kg, reps)` — compares a just-logged
  set against every prior working set for the same exercise

Because they're private to a router module, nothing else can reuse them.
FEAT-101 (PR history) needs exactly this logic. Copy-pasting it would
give two PR definitions that drift apart over time.

## What to do

1. Create `app/services/personal_records.py` and move both helpers into it
   as public functions: `estimated_1rm(...)` and `check_pr(...)`.
2. Update `app/routers/workouts.py` to import and call them from the service.
3. Keep the docstrings and the existing rules intact:
   - Main section only, `set_type == "working"` only
   - Sets without a weight or reps are never PRs
   - The first-ever working set for an exercise is not a PR
   - A heavier weight is a `"weight"` PR, which takes precedence over an
     `"estimated_1rm"` PR

## Out of scope

- The dashboard computes its own Epley 1RM in JavaScript
  (`app/templates/progress_dashboard.html`). Leave it alone. This ticket is
  backend only.
- No API, schema, or database changes.

## Acceptance criteria

- [ ] `POST /api/workout-logs` returns identical `is_pr` / `pr_type` values
      for identical input, before and after.
- [ ] `tests/test_pr_detection.py` passes **without modification**.
- [ ] Full test suite passes.
- [ ] The diff contains only the move and the import changes. No logic edits
      are mixed in.
