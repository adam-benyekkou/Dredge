"""Multi-channel notification service using Apprise"""

import apprise
import logging
import asyncio
from typing import Optional
from sqlmodel import Session
from app.models import AppSettings
from app.core.db import engine

logger = logging.getLogger(__name__)

async def send_notification(title: str, body: str, tags: Optional[str] = None):
    """Supress notifications in Demo Mode"""
    logger.info(f"[DEMO MODE] Notification suppressed: {title}")
    return
