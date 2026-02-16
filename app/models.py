"""Domain models for Dredge"""

from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, JSON, Column
from sqlalchemy import JSON as SAJSON


class ImageArtifact(SQLModel, table=True):
    """Docker image artifact model"""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    tags: List[str] = Field(default=[], sa_column=Column(SAJSON))
    size_bytes: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    digest: str = Field(default="", max_length=255)
