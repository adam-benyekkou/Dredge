"""Dredge FastAPI Application Entrypoint"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Initialize FastAPI app
app = FastAPI(
    title="Dredge",
    description="Docker FinOps & Lifecycle Management Tool",
    version="0.1.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure Jinja2 templates
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "app": "Dredge", "version": "0.1.0"}
