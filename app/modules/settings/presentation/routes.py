from fastapi import APIRouter

settings_router = APIRouter()

@settings_router.get("/")
async def get_settings():
    return {"currency": "USD", "theme": "nautical", "version": "1.0.0"}
