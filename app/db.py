"""Tiny SQLite helpers shared by both datasets (OPD and medicine supply chain)."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    """The exact current moment as ISO-8601 UTC with microseconds.

    Example: 2026-10-09T01:06:12.345678+00:00
    Fixed-width, so the text sorts in time order, and any tool can parse it.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (and create if needed) a database file. Use ':memory:' for tests."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # One shared connection per store; the store's lock serialises access to it.
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
