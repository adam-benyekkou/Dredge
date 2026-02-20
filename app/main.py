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
    """Render the login page"""
    # Check if already logged in
    token = request.cookies.get("access_token")
    if token:
        if token.startswith("Bearer "):
            token = token[len("Bearer "):]
        try:
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return RedirectResponse(url="/", status_code=302)
        except JWTError:
            pass
            
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    """Handle login form submission"""
    settings = session.get(AppSettings, 1)
    
    # Default admin/admin if settings not initialized (fallback)
    valid = False
    if settings:
        if username == settings.admin_username and verify_password(password, settings.admin_password):
            valid = True
    else:
        # Fallback for very first run if DB empty (though init_db should handle this)
        if username == "admin" and password == "admin":
             valid = True

    if not valid:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Invalid username or password"},
            status_code=401
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    
    # Create redirect response
    response = RedirectResponse(url="/", status_code=303)
    
    # Set cookie
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    
    return response

@app.post("/api/v1/auth/login")
async def login_api(
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
app.include_router(quarantine_router, dependencies=[Depends(get_current_user)])


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
