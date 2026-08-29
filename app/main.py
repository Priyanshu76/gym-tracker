from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
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
from app.routers import auth, admin, workouts, exercises, profile, plans
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(workouts.router)
app.include_router(exercises.router)
app.include_router(profile.router)
app.include_router(plans.router)


@app.get("/", response_class=HTMLResponse)
def weekly_lift_log_page(request: Request):
    return templates.TemplateResponse(request, "weekly_lift_log.html")


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html")


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(request: Request):
    return templates.TemplateResponse(request, "reset_password.html")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "progress_dashboard.html")


@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    return templates.TemplateResponse(request, "workout_logs.html")


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request):
    return templates.TemplateResponse(request, "onboarding.html")


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    return templates.TemplateResponse(request, "onboarding.html")


@app.get("/plans", response_class=HTMLResponse)
def plan_selection_page(request: Request):
    return templates.TemplateResponse(request, "plan_selection.html")


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Verifies the app is up AND can reach Postgres — not just that the process is alive."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "environment": settings.environment}


@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    """
    A mistyped URL or stale bookmark used to render raw {"detail":"Not Found"}
    JSON — looks like a crashed site to anyone who isn't a developer. API
    clients (/api/*) still get JSON, since that's the correct contract for
    them; only browser page navigation gets the styled fallback.

    Registered against Starlette's BASE HTTPException, not FastAPI's subclass
    of it — genuinely unmatched routes (no route pattern matches at all) are
    raised by Starlette's own router as the base class, so a handler
    registered only for the FastAPI subclass would silently miss them
    (caught this via a real failing test, not by inspection).
    """
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        return templates.TemplateResponse(request, "404.html", status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
