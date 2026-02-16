"""Database configuration and session management"""

from sqlmodel import create_engine, SQLModel, Session
import os

# SQLite database file path
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dredge.db")

# Create engine with WAL mode support and thread safety for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

def init_db():
    """Initialize the database and create tables.
    
    Sets up SQLite WAL mode for better concurrency and creates all
    tables defined in the models.
    """
    # Enable WAL mode for SQLite
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL;")
            connection.exec_driver_sql("PRAGMA synchronous=NORMAL;")
    
    SQLModel.metadata.create_all(engine)
    
    # Initialize default settings
    from app.models import AppSettings
    with Session(engine) as session:
        if not session.get(AppSettings, 1):
            settings = AppSettings(id=1)
            session.add(settings)
            session.commit()

def get_session():
    """Dependency for getting a database session.
    
    Yields:
        SQLModel Session object
    """
    with Session(engine) as session:
        yield session
