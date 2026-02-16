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
    """
    Send notifications via Apprise to configured channels.
    
    Channels are loaded from AppSettings (notification_urls).
    """
    # Fetch urls from DB
    with Session(engine) as session:
        settings = session.get(AppSettings, 1)
        if not settings or not settings.notification_urls:
            logger.debug("No notification channels configured.")
            return

        urls = [url.strip() for url in settings.notification_urls.split(',') if url.strip()]
        if not urls:
            return

    # Initialize Apprise
    apobj = apprise.Apprise()
    
    for url in urls:
        try:
            apobj.add(url)
        except Exception as e:
            logger.error(f"Failed to add notification URL {url}: {e}")

    # Run in thread pool since apprise notify can be blocking
    try:
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, 
            lambda: apobj.notify(
                title=title,
                body=body,
                tag=tags
            )
        )
        if success:
            logger.info(f"Notification sent: {title}")
        else:
            logger.warning(f"Failed to send some notifications: {title}")
            
    except Exception as e:
        logger.error(f"Error during notification broadcast: {e}")
