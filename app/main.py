from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
templates = Jinja2Templates(directory="app/templates")

# Routers get included here as each migration phase lands.
from app.routers import auth, admin, workouts, exercises
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(workouts.router)
app.include_router(exercises.router)


@app.get("/", response_class=HTMLResponse)
def weekly_lift_log_page(request: Request):
    return templates.TemplateResponse(request, "weekly_lift_log.html")


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Verifies the app is up AND can reach Postgres — not just that the process is alive."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "environment": settings.environment}
