"""Dredge FastAPI Application Entrypoint"""

import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.web.routes import router

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

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include web routes
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "app": "Dredge", "version": "0.1.0"}


@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logging.info("Dredge application starting...")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    logging.info("Dredge application shutting down...")
