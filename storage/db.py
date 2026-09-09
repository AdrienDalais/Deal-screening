"""Engine and session factory.

Everything that touches the database goes through here, so there is one
place that knows where the database lives and one place to change when
it stops being SQLite.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = "sqlite:///data/deals.db"


def database_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env")
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine(url: str | None = None, echo: bool = False) -> Engine:
    url = url or database_url()
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        # Relative paths in the URL are relative to the project root, not
        # to whatever directory the process happens to be started from.
        relative = url.removeprefix("sqlite:///")
        if not Path(relative).is_absolute():
            absolute = PROJECT_ROOT / relative
            absolute.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{absolute}"
    return create_engine(url, echo=echo, future=True)


def get_sessionmaker(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)
