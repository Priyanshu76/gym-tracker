# Gym Tracker — FastAPI + Postgres rewrite

Migrating off n8n + Google Sheets to a proper backend: FastAPI, PostgreSQL,
SQLAlchemy/Alembic, JWT auth via httpOnly cookies.

## Local development

```bash
cp .env.example .env        # fill in real values, especially JWT_SECRET_KEY
docker compose up --build   # starts Postgres + the API with live reload
```

Once running:
- API health check: http://localhost:8000/api/health
- Interactive API docs (dev only): http://localhost:8000/api/docs

### Running migrations

```bash
docker compose exec api alembic revision --autogenerate -m "initial schema"
docker compose exec api alembic upgrade head
```

## Branching model

- `prod` — production. Only updated via PR from `dev`. Auto-deploys to OCI on merge (once CI/CD lands).
- `dev` — integration branch. Feature branches are cut from here, merged back here.
- Feature branches: `dev-<short-description>`, e.g. `dev-auth-migration`.

## Migration roadmap (from the old n8n workflow)

- [x] Phase 0 — repo scaffold, Docker Compose, DB models, Alembic, health check
- [x] Phase 1 — auth: signup, login (JWT httpOnly cookie), email verify, admin approve/reject, forgot/reset password, forced reset
- [x] Phase 2a — workout-logs and custom-exercises endpoints
- [x] Phase 2b — Weekly_Lift_Log page migrated to Jinja2, served at `/`, cookie-based auth (no client-side token at all)
- [x] Phase 2c — Signup and Reset Password pages migrated to Jinja2 (`/signup`, `/reset-password`), full loop verified end-to-end including real error-shape handling
- [ ] Phase 3 — migrate Progress_Dashboard + Workout_Logs pages
- [x] Phase 4 — Google Sheets -> Postgres migration script (migrations_data/migrate_from_sheets.py), transformation logic fully tested; live Sheets API call untested (no network path from here to Google's API)
- [ ] Phase 5 — GitHub Actions CD (auto-deploy prod on merge), new OCI instance deployment

## Notes on what changed vs. the n8n version

- Auth moves from a static API key / query-param session token to JWT in an
  **httpOnly cookie** — closes the XSS token-theft gap we'd discussed earlier
  but didn't fully close in the n8n version.
- Sessions are still tracked in a DB table (not just JWT-stateless) so a
  password reset can actually revoke existing sessions — the n8n version
  couldn't do this cleanly.
- The old Field1/Field2/Field3 Label/Value columns (for Warmup/Stretch
  metrics) collapse into a single Postgres JSON column — no more hard 3-field
  ceiling per exercise.
- Username/email uniqueness is enforced by the database itself, not
  application-level lookups — removes a whole class of race conditions.
