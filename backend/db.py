from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import JSON


def _json_type(engine: Engine):
    # Use JSONB on Postgres, generic JSON elsewhere (e.g., SQLite for tests)
    if engine.dialect.name == "postgresql":
        return JSONB
    return JSON


@dataclass(frozen=True)
class Database:
    engine: Engine
    SessionLocal: sessionmaker
    metadata: MetaData
    tables: Dict[str, Table]


def create_database(database_url: str) -> Database:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
    )

    metadata = MetaData()
    json_col = _json_type(engine)

    isolation_log = Table(
        "isolation_log",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("agent_name", String(255), nullable=False, index=True),
        Column("isolated_at", DateTime(timezone=True), server_default=func.now()),
        Column("reason", String(500)),
        Column("status", String(50), server_default="ISOLATED", index=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
    )

    blocked_messages = Table(
        "blocked_messages",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("sender", String(255), nullable=False, index=True),
        Column("recipient", String(255)),
        Column("score", Float),
        Column("layers", json_col),
        Column("blocked_at", DateTime(timezone=True), server_default=func.now(), index=True),
    )

    agent_baselines = Table(
        "agent_baselines",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("agent_name", String(255), unique=True, nullable=False, index=True),
        Column("centroid", Text),
        Column("samples", Integer, server_default="0"),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    clean_messages = Table(
        "clean_messages",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("sender", String(255)),
        Column("recipient", String(255)),
        Column("score", Float),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), index=True),
    )

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    tables = {
        "isolation_log": isolation_log,
        "blocked_messages": blocked_messages,
        "agent_baselines": agent_baselines,
        "clean_messages": clean_messages,
    }

    return Database(engine=engine, SessionLocal=SessionLocal, metadata=metadata, tables=tables)


def ensure_schema(db: Database) -> None:
    """Create tables if missing (safe to call at startup)."""
    db.metadata.create_all(db.engine)


def db_session(db: Database) -> Session:
    return db.SessionLocal()


def safe_commit(session: Session) -> None:
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
