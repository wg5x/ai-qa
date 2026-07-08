from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def ensure_sqlite_parent_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database not in (None, "", ":memory:"):
        database_path = Path(url.database)
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str):
    ensure_sqlite_parent_directory(database_url)
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False}
        if database_url.startswith("sqlite")
        else {},
    )


database_url = settings.database_url
engine = create_database_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def configure_database(new_database_url: str) -> None:
    global database_url, engine, SessionLocal

    engine.dispose()
    database_url = new_database_url
    engine = create_database_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
