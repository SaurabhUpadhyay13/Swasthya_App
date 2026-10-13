"""Doctors and their login sessions (tables live in data/opd.db, next to the OPD data).

A session token is a random string given to the browser. Only its SHA-256 hash is stored,
so a leaked database file cannot be used to log in.
"""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import RLock

from app.db import utc_now
from app.schemas.doctors import Doctor
from app.schemas.opd import DEPARTMENTS, Department

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL COLLATE NOCASE,
    medical_id TEXT NOT NULL UNIQUE COLLATE NOCASE,
    department TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS doctor_sessions (
    token_hash TEXT PRIMARY KEY,
    doctor_id  INTEGER NOT NULL REFERENCES doctors(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""

SESSION_HOURS = 12  # roughly one shift


def _clean(text: str) -> str:
    return " ".join(text.split())


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _to_doctor(row: sqlite3.Row) -> Doctor:
    values = dict(row)
    return Doctor(
        id=values["id"],
        name=values["name"],
        medical_id=values["medical_id"],
        department=values["department"],
        department_name=DEPARTMENTS[Department(values["department"])][0],
    )


class DoctorStore:
    """Shares the OPD store's connection and lock (see OpdStore)."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self._conn = conn
        self._lock = lock

    def add(self, name: str, medical_id: str, department: Department) -> Doctor:
        """Register a doctor. Done by an administrator (python -m app.cli add-doctor)."""
        try:
            with self._lock, self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO doctors (name, medical_id, department, created_at) VALUES (?, ?, ?, ?)",
                    (_clean(name), _clean(medical_id), department.value, utc_now()),
                )
                row = self._conn.execute("SELECT * FROM doctors WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise ValueError(f"Medical ID {medical_id} is already registered.") from None
        return _to_doctor(row)

    def login(self, name: str, medical_id: str) -> tuple[str, datetime, Doctor] | None:
        """Return (session token, expiry, doctor) when name and medical ID match, else None."""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM doctors WHERE name = ? AND medical_id = ?", (_clean(name), _clean(medical_id))
            ).fetchone()
            if row is None:
                return None
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=SESSION_HOURS)
            token = secrets.token_urlsafe(32)
            self._conn.execute("DELETE FROM doctor_sessions WHERE expires_at <= ?", (utc_now(),))  # housekeeping
            self._conn.execute(
                "INSERT INTO doctor_sessions (token_hash, doctor_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (_hash(token), row["id"], utc_now(), expires_at.isoformat(timespec="microseconds")),
            )
            return token, expires_at, _to_doctor(row)

    def from_session(self, token: str) -> Doctor | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT d.* FROM doctor_sessions s JOIN doctors d ON d.id = s.doctor_id"
                " WHERE s.token_hash = ? AND s.expires_at > ?",
                (_hash(token), utc_now()),
            ).fetchone()
        return _to_doctor(row) if row else None

    def logout(self, token: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM doctor_sessions WHERE token_hash = ?", (_hash(token),))
