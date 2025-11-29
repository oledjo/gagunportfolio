from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel
from typing import Generator
import os

# SQLite database file - use environment variable for production
# Default to portfolio.db in current directory for local development
db_path = os.getenv("DATABASE_PATH", "portfolio.db")
DATABASE_URL = f"sqlite:///{db_path}"

# Create engine
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables():
    """Create database and tables"""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Get database session"""
    with Session(engine) as session:
        yield session

