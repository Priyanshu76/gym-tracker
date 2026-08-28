from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

settings = get_settings()

app = FastAPI(
    title="Gym Tracker API",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,  # hide interactive docs in prod
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers get included here as each migration phase lands. Empty for now —
# Phase 0 is just "does the app boot and talk to Postgres."
# from app.routers import auth, workouts, exercises, admin
# app.include_router(auth.router)
# app.include_router(workouts.router)
# app.include_router(exercises.router)
# app.include_router(admin.router)


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Verifies the app is up AND can reach Postgres — not just that the process is alive."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "environment": settings.environment}
