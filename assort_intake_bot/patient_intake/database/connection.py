"""Database connection manager for SQLite."""

import sqlite3
from pathlib import Path

from .schema import SCHEMA

DB_PATH = Path(__file__).parent.parent / "patient_intake.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database() -> None:
    """Initialize the database with schema."""
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
