from fastapi import FastAPI, Depends, HTTPException, status, Response, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
import logging
from sqlmodel import Session
from datetime import timedelta

# Import Modular Routers (DDD)
from app.modules.images.presentation.routes import image_router
from app.modules.settings.presentation.routes import settings_router
# Existing UI router
from app.web.routes import router as web_router
from app.web.routes_quarantine import router as quarantine_router

from app.core.db import init_db, get_session
from app.models import AppSettings, verify_password
from app.core.auth_jwt import get_current_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
from jose import jwt, JWTError
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    PROMETHEUS_ENABLED = True
except ImportError:
    PROMETHEUS_ENABLED = False

from app.core.logging import setup_logging
setup_logging()

# Initialize FastAPI app
app = FastAPI(
    title="Dredge",
    description="Docker FinOps & Lifecycle Management Tool",
    version="0.1.0",
)

templates = Jinja2Templates(directory="templates")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle 401 Unauthorized by redirecting to login"""
    if exc.status_code == 401:
        # Handle HTMX requests - Force full page redirect
        if request.headers.get("HX-Request"):
            response = Response(status_code=200)
            response.headers["HX-Redirect"] = "/auth/login"
            return response

        # Handle Standard Browser requests
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/auth/login", status_code=302)
            
    # Default behavior for other errors or JSON clients
    return JSONResponse(
        content={"detail": exc.detail}, 
        status_code=exc.status_code
    )

@app.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Redirect login to dashboard for demo"""
    return RedirectResponse(url="/", status_code=302)
@app.post("/auth/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    """Redirect login to dashboard for demo"""
    return RedirectResponse(url="/", status_code=303)
@app.post("/api/v1/auth/login")
async def login_api():
    """Mock API login for demo"""
    return {"access_token": "demo_token", "token_type": "bearer"}

# Mount static files for the UI
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# Router Strategy: Aggregation
# ---------------------------------------------------------

# API V1 Routes (Modular DDD)
app.include_router(
    image_router, 
    prefix="/api/v1/images", 
    tags=["Images"]
)

app.include_router(
    settings_router, 
    prefix="/api/v1/settings", 
    tags=["Settings"]
)
# Web/UI Routes (HTMX)
app.include_router(web_router)
app.include_router(quarantine_router)

# Initialize Prometheus instrumentation if available
if PROMETHEUS_ENABLED:
    Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "app": "Dredge", "version": "0.1.0"}


@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logging.info("Dredge application starting...")
    # Demo mode: restore DB from snapshot before init so we always start clean
    import os, shutil
    _here = os.path.dirname(os.path.abspath(__file__))
    snapshot = os.path.abspath(os.path.join(_here, '../scripts/demo_snapshot.db'))
    db_path = os.path.abspath(os.path.join(_here, '../dredge.db'))
    if os.path.exists(snapshot):
        shutil.copy(snapshot, db_path)
        logging.info("Demo DB restored from snapshot on startup.")
    init_db()
    logging.info("Database initialized.")
    from app.core.scheduler import start_scheduler
    start_scheduler()
    logging.info("Policy scheduler initialized.")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    logging.info("Dredge application shutting down...")
    
    # Shutdown scheduler gracefully
    from app.core.scheduler import shutdown_scheduler
    shutdown_scheduler()
