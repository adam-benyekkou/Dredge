from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
import logging
from sqlmodel import Session
from datetime import timedelta

# Import Modular Routers (DDD)
from app.modules.images.presentation.routes import image_router
from app.modules.settings.presentation.routes import settings_router
# Existing UI router
from app.web.routes import router as web_router

from app.core.db import init_db, get_session
from app.models import AppSettings, verify_password
from app.core.auth_jwt import get_current_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize FastAPI app
app = FastAPI(
    title="Dredge",
    description="Docker FinOps & Lifecycle Management Tool",
    version="0.1.0",
)

@app.post("/api/v1/auth/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    settings = session.get(AppSettings, 1)
    if not settings or form_data.username != settings.admin_username or not verify_password(form_data.password, settings.admin_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": settings.admin_username}, expires_delta=access_token_expires
    )
    
    # Set cookie for UI/HTMX
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

# Mount static files for the UI
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# Router Strategy: Aggregation
# ---------------------------------------------------------

# API V1 Routes (Modular DDD)
app.include_router(
    image_router, 
    prefix="/api/v1/images", 
    tags=["Images"],
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    settings_router, 
    prefix="/api/v1/settings", 
    tags=["Settings"],
    dependencies=[Depends(get_current_user)]
)

# Web/UI Routes (HTMX)
app.include_router(web_router, dependencies=[Depends(get_current_user)])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "app": "Dredge", "version": "0.1.0"}


@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logging.info("Dredge application starting...")
    init_db()
    logging.info("Database initialized.")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    logging.info("Dredge application shutting down...")
