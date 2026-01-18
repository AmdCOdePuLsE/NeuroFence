#!/usr/bin/env python3
"""NeuroFence Database Initialization.

Creates the target PostgreSQL database (if missing) and ensures all tables exist.

Notes:
- Uses psycopg2 to CREATE DATABASE (Postgres-only operation).
- Uses SQLAlchemy metadata to create tables/indexes idempotently.
"""

from __future__ import annotations

import logging
import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

from backend.config import get_settings
from backend.db import create_database, ensure_schema


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neurofence.init_db")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def create_database_if_missing() -> None:
    settings = get_settings()

    db_host = _env("DB_HOST", "localhost")
    db_port = _env("DB_PORT", "5432")
    db_name = _env("DB_NAME", "neurofence_hack")
    db_user = _env("DB_USER", "postgres")
    db_password = _env("DB_PASSWORD", "postgres")

    logger.info("📦 Ensuring database '%s' exists...", db_name)

    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
            exists = cursor.fetchone() is not None
            if not exists:
                cursor.execute(f"CREATE DATABASE {db_name};")
                logger.info("✅ Database '%s' created successfully", db_name)
            else:
                logger.info("ℹ️  Database '%s' already exists", db_name)

        conn.close()
    except Exception as e:
        logger.error("❌ Error creating database: %s", e)
        raise


def create_tables() -> None:
    settings = get_settings()
    logger.info("📦 Ensuring tables exist via SQLAlchemy...")
    db = create_database(settings.database_url)
    ensure_schema(db)
    logger.info("✅ All tables ensured")


def verify_connection() -> bool:
    settings = get_settings()
    try:
        db = create_database(settings.database_url)
        with db.engine.connect() as conn:
            version_row = conn.exec_driver_sql("SELECT version();").fetchone()
        version = version_row[0] if version_row else "unknown"
        logger.info("✅ Database connection verified: %s", version)
        return True
    except Exception as e:
        logger.error("❌ Database connection failed: %s", e)
        return False


if __name__ == "__main__":
    load_dotenv()

    logger.info("🚀 NeuroFence Database Initialization Starting...")

    logger.info("📦 Step 1: Creating database...")
    create_database_if_missing()

    logger.info("📦 Step 2: Creating tables...")
    create_tables()

    logger.info("📦 Step 3: Verifying connection...")
    if verify_connection():
        logger.info("✅ Database initialization complete! Ready for NeuroFence.")
    else:
        raise SystemExit(1)
