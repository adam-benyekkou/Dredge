"""Dredge FastAPI Application Entrypoint"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.web.routes import router

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
