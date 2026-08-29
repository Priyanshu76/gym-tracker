# Future Roadmap — Deferred Features

Everything here was explicitly deferred during the platform-analysis pass
(2026-08-29) as too large to build with real testing rigor alongside the
bug fixes and core features that shipped in that same effort. Each item is
broken into independently-actionable tasks, roughly in the order they'd
naturally get built (later tasks in a section often depend on earlier ones).

Nothing here is started. Priority/order across sections is a suggestion,
not a commitment — reorder freely based on what actually matters most once
real users are on the pilot.

---

## 1. Superset / circuit grouping

Exercises currently log as flat, independent items — no way to say "these
two are a superset, done back-to-back."

- [ ] Add a `superset_group_id` (nullable UUID) column to `PlanExercise`,
      shared by every exercise in the same superset
- [ ] Generator support: when building a day, optionally pair compatible
      exercises (opposing muscle groups, e.g. push+pull) into a superset
      rather than always sequential singles
- [ ] Log page UI: render superset-grouped exercises as one visual block
      with a shared "next" flow instead of separate cards
- [ ] Workout Logs table: visually indicate which entries belonged to the
      same superset (e.g. a connecting bracket or shared background tint)
- [ ] Dashboard: decide whether superset sets should count differently in
      volume/PR calculations (they shouldn't — same math, just a UI grouping
      concern — but worth confirming explicitly rather than assuming)

## 2. Body-metrics history

Height/weight/age currently live only as a static profile snapshot, never
tracked over time, despite the dashboard already having a charting system
that could support this cheaply.

- [ ] New `BodyMetricLog` model: `user_id`, `logged_at`, `weight_kg`,
      `height_cm` (nullable, rarely changes), `notes` (optional)
- [ ] `POST /api/body-metrics`, `GET /api/body-metrics` (ownership-scoped,
      same pattern as workout logs)
- [ ] Decide UI entry point: a dedicated "Log weight" quick-action from the
      dashboard or profile page, separate from workout logging
- [ ] Dashboard: new chart (reuse the existing progression-chart pattern)
      showing bodyweight trend over the selected date range
- [ ] Consider: should `UserProfile.weight_kg` become derived (latest
      `BodyMetricLog` entry) rather than a separately-edited static field,
      to avoid the two going out of sync? Worth deciding before building,
      not after.

## 3. Real exercise library UI (search/autocomplete)

The 58-exercise library exists in the database (used by the plan generator)
but the frontend "swap options" UI still only shows 2-4 hardcoded alternates
plus a free-text "add your own" — it never queries the real library.

- [ ] `GET /api/exercises?search=&muscle_group=&equipment=` — searchable
      endpoint over the existing `Exercise` table (the table already has
      everything needed: muscle_group, equipment_needed, split_category)
- [ ] Frontend: replace the free-text "+ Add" custom-exercise input with a
      searchable autocomplete hitting this endpoint, falling back to free
      text only if genuinely not found in the library
- [ ] Decide: should library-sourced swaps still go through the existing
      `CustomExercise` table, or does swapping to a known library exercise
      need a different, simpler code path than the current
      user-typed-name flow?
- [ ] Exercise detail: since the library already has `muscle_group`,
      `movement_pattern`, `equipment_needed`, consider surfacing these as a
      short info panel when picking a swap, not just a bare name

## 4. Deload / periodization automation

The in-app Guidelines already say "keep primary exercises stable for 6-8
weeks," but nothing tracks weeks-on-exercise or nudges an actual deload.

- [ ] Track "weeks on current working weight" per exercise per user — this
      needs a definition first: is it consecutive weeks logged, or calendar
      weeks since the exercise was first added to an active plan?
- [ ] `GET /api/plans/deload-suggestions` (or fold into an existing
      dashboard-data endpoint) — surfaces exercises that have crossed the
      threshold
- [ ] Dashboard or log-page banner: "You've been on Barbell Back Squat for
      7 weeks — consider a deload" style nudge
- [ ] Decide the actual deload logic once flagged: is this purely
      informational (nudge only, no automatic plan change), or should it
      offer to auto-generate a deload week (reduced volume/intensity) via
      the existing plan generator? Start with informational-only; automatic
      deload-plan generation is a meaningfully bigger follow-up.

## 5. PR history / progression detail

Personal Records cards currently show only the single most-recent PR per
exercise, not a history of how it's progressed.

- [ ] Decide the visual: a small inline sparkline per PR card (reuses
      Chart.js, already loaded) vs. a "beat by +5kg" delta line vs. a
      dedicated per-exercise history view
- [ ] If sparkline: needs a lightweight per-exercise time series query —
      can likely reuse the existing progression-chart data-shaping logic
      already built for the Main Lifts tab, rather than writing new
      aggregation from scratch

## 6. Admin approval dashboard

Signup approval is currently a manual, out-of-band process — an email
notification with approve/reject links, no in-app admin view at all.

- [ ] `GET /api/admin/pending-signups` — list view for whoever's approving
- [ ] `GET /api/admin/users` — basic user list (for visibility into who has
      accounts, useful once this isn't just one admin from memory)
- [ ] A simple `/admin` page (reuse the existing dark theme + component
      patterns) rendering these, with approve/reject buttons calling the
      already-existing `/api/approve-signup` / `/api/reject-signup` logic
      (no backend change needed there, just a UI in front of it)
- [ ] Role-based access: only worth building once there's a second admin —
      currently every "admin" action is gated by a single shared
      `ADMIN_CREATE_USER_KEY`/email-link token, which is fine for one
      person and needs rethinking (real roles on the `User` model) the
      moment a second admin exists

## 7. Set-type-aware analytics

`set_type` (working/warmup/drop_set/amrap/failure) was added to the data
model and logging UI, but nothing downstream actually *uses* it yet — PRs
and volume calculations currently treat every set identically regardless
of type.

- [ ] PR calculation: exclude `warmup` and `drop_set` sets from "personal
      record" consideration — a warm-up set at a lighter weight shouldn't
      ever register as a PR, and a drop-set's reduced-weight portion
      shouldn't either
- [ ] Volume charts: decide whether to include/exclude warm-up sets from
      the "total volume" figure (real training-log apps vary on this —
      worth an explicit decision, not a default)
- [ ] Workout Logs table: visually distinguish set types (a small colored
      tag next to weight/reps) rather than requiring a click into edit mode
      to see it

## 8. Units toggle (kg / lb)

Everything is kg-only right now — fine for the current pilot audience, a
real blocker the moment this opens to non-metric users.

- [ ] Add a `unit_preference` field to `UserProfile` (kg/lb)
- [ ] Central conversion helper (likely a small shared JS module, similar
      in spirit to `icons.js`) rather than scattering `* 2.20462` across
      every template
- [ ] Decide storage strategy: store everything in kg server-side always
      (recommended — avoids ever needing to migrate stored data if the
      preference changes) and convert only at display/input time
- [ ] Every numeric weight display and input across all pages needs the
      conversion applied — this touches more surface area than it sounds
      like at first (log page, dashboard charts, PR cards, CSV export,
      workout logs table)

## 9. Light theme

Dark-mode only currently. This is a straightforward but *wide* task, not a
hard one — every template's CSS custom properties need a second value set.

- [ ] Define a light-theme token set mirroring the existing dark one
      (`--bg`, `--surface`, `--chalk`, `--steel`, etc.)
- [ ] Add a theme toggle (profile setting, persisted — likely alongside
      `unit_preference` above) and a `data-theme` attribute or similar
      driving which token set applies
- [ ] Visual QA pass across every page once toggled — icons, chart colors,
      and the inlined Chart.js color config (`Chart.defaults.color` etc.,
      currently hardcoded for dark) all need to respond to the active theme

## 10. Plate calculator

Genuinely small/self-contained relative to everything else here — a good
candidate to actually pull forward and do sooner rather than later.

- [ ] Pure client-side: given a target total weight and a bar weight
      (standard Olympic bar = 20kg, adjustable), compute which plates go on
      each side from a standard plate set (25/20/15/10/5/2.5/1.25kg)
- [ ] Surface it inline in the log page — e.g. a small "plates" icon next
      to the weight input that expands a computed breakdown
- [ ] No backend changes needed at all — this is entirely frontend logic

## 11. Warm-up ramp-up suggestions

Auto-generate warm-up set weights leading up to a top set (e.g. bar, 40%,
60%, 80%, top set).

- [ ] Pure calculation off the planned/target top-set weight already shown
      on each exercise card — no new data model needed
- [ ] Standard percentage-based ramp scheme (configurable steps, sane
      defaults) surfaced as a suggestion above the first set row
- [ ] Decide whether these ramp-up sets should be loggable as their own
      rows (tagged `set_type=warmup`, which already exists) or purely
      advisory/display-only

## 12. Larger infrastructure/product features (lower priority, biggest lift each)

These are all genuinely multi-week efforts on their own — listed for
completeness, not because any should be started soon.

- [ ] **Wearable/health integration** — Apple Health / Google Fit sync for
      bodyweight and cardio heart-rate data. Requires OAuth integration
      with each platform's SDK and is realistically its own project.
- [ ] **Push notifications / reminders** — "you haven't logged today,"
      streak reminders. Requires a notification delivery service (web push
      or a mobile wrapper) that doesn't exist in this stack at all yet.
- [ ] **Social layer** — sharing summaries, following streaks, simple
      leaderboards. Needs its own data model (follows/friendships) and a
      privacy/opt-in design pass before any code, given this started as a
      personal project.
- [ ] **PWA / offline-first** — add-to-homescreen, offline logging that
      syncs when back online. Requires a service worker, an offline data
      queue, and conflict-resolution logic for syncing — a substantial
      rework of how the frontend talks to the backend, not an additive
      feature.
- [ ] **Exercise media** — form-check GIFs/videos per exercise. Needs either
      licensed content or original recording, plus a CDN/storage story
      (Postgres is not where video belongs) — a content and infrastructure
      project as much as a code one.
- [ ] **Multi-goal plan generation depth** — asking goal-specific follow-up
      questions during onboarding (target lifts, weak points, session
      length) rather than the current single goal+experience+equipment
      input set. Worth revisiting once there's real usage data on whether
      the current generator's output quality actually needs this, rather
      than speculatively building it now.

---

## Suggested order, if picking somewhere to start

Roughly cheapest-to-build and highest-value-for-a-single-user-pilot first:

1. Plate calculator (#10) — small, self-contained, no backend
2. Set-type-aware analytics (#7) — the data already exists, just needs to
   be used
3. Body-metrics history (#2) — reuses existing charting patterns directly
4. PR history/sparkline (#5) — same reason
5. Real exercise library UI (#3) — meaningfully improves the swap
   experience with infrastructure that already exists
6. Everything else, roughly in the order listed above

The three "larger infrastructure" items in #12 and the units/theme toggles
(#8, #9) are reasonable to leave until there's actual user demand signaling
they're worth the investment, rather than building them speculatively.
