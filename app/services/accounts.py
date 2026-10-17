"""Logins for OPD staff and patients (tables live in data/opd.db, next to the OPD data).

Staff log in with name + staff ID, like doctors. Patients use their phone number and a password.
A patient gets a password only through a one-time code handed over by the OPD desk, so a stranger
who merely knows a phone number cannot claim someone's health record.

Session tokens are random strings given to the browser; only their SHA-256 hash is stored.
"""

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from threading import RLock

from app.db import utc_now
from app.errors import api_error
from app.schemas.accounts import Staff
from app.schemas.admin import Admin, StaffMember

SCHEMA = """
CREATE TABLE IF NOT EXISTS staff (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL COLLATE NOCASE,
    staff_id   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    admin_id        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT NOT NULL,               -- salt$scrypt hash, never the password
    failed_attempts INTEGER NOT NULL DEFAULT 0,  -- wrong passwords in a row
    locked_until    TEXT,                        -- set after too many wrong passwords, UTC
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS patient_accounts (
    phone         TEXT PRIMARY KEY REFERENCES patients(phone),
    password_hash TEXT NOT NULL,                 -- salt$scrypt hash, never the password
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS access_codes (
    phone      TEXT PRIMARY KEY REFERENCES patients(phone),   -- one live code per patient
    code_hash  TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signup_codes (
    phone      TEXT PRIMARY KEY,                 -- a phone number that is not yet in patients
    name       TEXT NOT NULL,
    age        INTEGER NOT NULL,
    code_hash  TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS account_sessions (
    token_hash TEXT PRIMARY KEY,
    role       TEXT NOT NULL,                    -- 'staff', 'patient' or 'admin'
    subject    TEXT NOT NULL,                    -- staff.id, admins.id or patients.phone
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""

STAFF_SESSION_HOURS = 12  # roughly one shift
ADMIN_SESSION_HOURS = 8
MAX_ADMIN_FAILURES = 5  # wrong passwords in a row before the account is locked
ADMIN_LOCK_MINUTES = 5
PATIENT_SESSION_HOURS = 24
CODE_HOURS = 24
MAX_CODE_ATTEMPTS = 5
SIGNUP_CODE_SECONDS = 60


def _clean(text: str) -> str:
    return " ".join(text.split())


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(candidate.hex(), digest)


_DUMMY_HASH = hash_password("not-a-real-password")  # unknown phones cost the same time as wrong passwords


class Sessions:
    """Login sessions for both roles. Shares the OPD store's connection and lock."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self._conn = conn
        self._lock = lock

    def start(self, role: str, subject: str, hours: int) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM account_sessions WHERE expires_at <= ?", (utc_now(),))  # housekeeping
            self._conn.execute(
                "INSERT INTO account_sessions (token_hash, role, subject, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (_sha(token), role, subject, utc_now(), expires_at.isoformat(timespec="microseconds")),
            )
        return token, expires_at

    def subject(self, role: str, token: str) -> str | None:
        """Who this token belongs to, or None when it is unknown, expired or for the other role."""
        with self._lock:
            row = self._conn.execute(
                "SELECT subject FROM account_sessions WHERE token_hash = ? AND role = ? AND expires_at > ?",
                (_sha(token), role, utc_now()),
            ).fetchone()
        return row["subject"] if row else None

    def end(self, token: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM account_sessions WHERE token_hash = ?", (_sha(token),))

    def end_all(self, role: str, subject: str) -> None:
        """Log a person out everywhere, e.g. after their password was reset."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM account_sessions WHERE role = ? AND subject = ?", (role, subject))


class StaffStore:
    def __init__(self, conn: sqlite3.Connection, lock: RLock, sessions: Sessions) -> None:
        self._conn = conn
        self._lock = lock
        self._sessions = sessions

    def add(self, name: str, staff_id: str) -> Staff:
        """Register an OPD staff member. Done by an administrator (python -m app.cli add-staff)."""
        try:
            with self._lock, self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO staff (name, staff_id, created_at) VALUES (?, ?, ?)",
                    (_clean(name), _clean(staff_id), utc_now()),
                )
                row = self._conn.execute("SELECT * FROM staff WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise ValueError(f"Staff ID {staff_id} is already registered.") from None
        return Staff(**dict(row))

    def all(self) -> list[StaffMember]:
        with self._lock:
            rows = self._conn.execute("SELECT id, name, staff_id, created_at FROM staff ORDER BY name").fetchall()
        return [StaffMember(**dict(row)) for row in rows]

    def login(self, name: str, staff_id: str) -> tuple[str, datetime, Staff] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM staff WHERE name = ? AND staff_id = ?", (_clean(name), _clean(staff_id))
            ).fetchone()
        if row is None:
            return None
        token, expires_at = self._sessions.start("staff", str(row["id"]), STAFF_SESSION_HOURS)
        return token, expires_at, Staff(**dict(row))

    def from_session(self, token: str) -> Staff | None:
        subject = self._sessions.subject("staff", token)
        if subject is None:
            return None
        with self._lock:
            row = self._conn.execute("SELECT * FROM staff WHERE id = ?", (int(subject),)).fetchone()
        return Staff(**dict(row)) if row else None

    def logout(self, token: str) -> None:
        self._sessions.end(token)


class AdminStore:
    """Hospital administrators. Unlike doctors and staff they log in with an ID *and a password*, because
    an administrator can see everything and add people. Five wrong passwords in a row lock the account briefly."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock, sessions: Sessions) -> None:
        self._conn = conn
        self._lock = lock
        self._sessions = sessions

    def add(self, name: str, admin_id: str, password: str) -> Admin:
        """Register an administrator (python -m app.cli add-admin)."""
        if len(password) < 8:
            raise ValueError("The password must be at least 8 characters.")
        try:
            with self._lock, self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO admins (name, admin_id, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (_clean(name), _clean(admin_id), hash_password(password), utc_now()),
                )
                row = self._conn.execute("SELECT id, name, admin_id FROM admins WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise ValueError(f"Admin ID {admin_id} is already registered.") from None
        return Admin(**dict(row))

    def login(self, admin_id: str, password: str) -> tuple[str, datetime, Admin] | None:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM admins WHERE admin_id = ?", (_clean(admin_id),)).fetchone()
            if row and row["locked_until"] and row["locked_until"] > utc_now():
                raise api_error(429, "too_many_attempts", "Too many wrong passwords. Please try again in a few minutes.")
            ok = check_password(password, row["password_hash"] if row else _DUMMY_HASH) and row is not None
            if not ok:
                if row:
                    failures = row["failed_attempts"] + 1
                    locked = None
                    if failures >= MAX_ADMIN_FAILURES:
                        failures = 0
                        locked = (datetime.now(timezone.utc) + timedelta(minutes=ADMIN_LOCK_MINUTES)).isoformat(
                            timespec="microseconds"
                        )
                    self._conn.execute(
                        "UPDATE admins SET failed_attempts = ?, locked_until = ? WHERE id = ?", (failures, locked, row["id"])
                    )
                return None
            self._conn.execute("UPDATE admins SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (row["id"],))
        token, expires_at = self._sessions.start("admin", str(row["id"]), ADMIN_SESSION_HOURS)
        return token, expires_at, Admin(id=row["id"], name=row["name"], admin_id=row["admin_id"])

    def from_session(self, token: str) -> Admin | None:
        subject = self._sessions.subject("admin", token)
        if subject is None:
            return None
        with self._lock:
            row = self._conn.execute("SELECT id, name, admin_id FROM admins WHERE id = ?", (int(subject),)).fetchone()
        return Admin(**dict(row)) if row else None

    def logout(self, token: str) -> None:
        self._sessions.end(token)


class PatientAccounts:
    def __init__(self, conn: sqlite3.Connection, lock: RLock, sessions: Sessions) -> None:
        self._conn = conn
        self._lock = lock
        self._sessions = sessions

    def issue_code(self, phone: str) -> tuple[str, str, datetime] | None:
        """A fresh 6-digit code for a patient who has visited. Replaces any earlier code.

        Returns (code, patient name, expiry), or None when the phone number is not a known patient.
        The same code also resets the password of a patient who already has an account.
        """
        code = f"{secrets.randbelow(10**6):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=CODE_HOURS)
        with self._lock, self._conn:
            patient = self._conn.execute("SELECT name FROM patients WHERE phone = ?", (phone,)).fetchone()
            if patient is None:
                return None
            self._conn.execute(
                "INSERT INTO access_codes (phone, code_hash, attempts, created_at, expires_at) VALUES (?, ?, 0, ?, ?)"
                " ON CONFLICT(phone) DO UPDATE SET code_hash = excluded.code_hash, attempts = 0,"
                " created_at = excluded.created_at, expires_at = excluded.expires_at",
                (phone, _sha(f"{phone}:{code}"), utc_now(), expires_at.isoformat(timespec="microseconds")),
            )
        return code, patient["name"], expires_at

    def set_password(self, phone: str, password: str) -> None:
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO patient_accounts (phone, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(phone) DO UPDATE SET password_hash = excluded.password_hash, updated_at = excluded.updated_at",
                (phone, hash_password(password), now, now),
            )

    def activate(self, phone: str, code: str, password: str) -> bool:
        """Check the one-time code and, if right, save the patient's chosen password."""
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM access_codes WHERE phone = ?", (phone,)).fetchone()
            if row is None or row["expires_at"] <= utc_now() or row["attempts"] >= MAX_CODE_ATTEMPTS:
                return False
            if not hmac.compare_digest(row["code_hash"], _sha(f"{phone}:{code}")):
                self._conn.execute("UPDATE access_codes SET attempts = attempts + 1 WHERE phone = ?", (phone,))
                return False
            self._conn.execute("DELETE FROM access_codes WHERE phone = ?", (phone,))  # a code works once
        self.set_password(phone, password)
        self._sessions.end_all("patient", phone)  # a reset must also remove whoever held the old password
        return True

    # ---- Self sign-up for a brand-new patient -------------------------------------------
    # The code is shown on the patient's own screen and expires after 60 seconds. It proves a person (not a
    # script) is at the screen; it does NOT prove they own the phone number. That is why self sign-up is allowed
    # only for phone numbers the hospital has never seen. A number with an existing record needs the OPD desk's code.

    def signup_start(self, phone: str, name: str, age: int) -> str:
        code = f"{secrets.randbelow(10**6):06d}"
        now = datetime.now(timezone.utc)
        with self._lock, self._conn:
            if self._conn.execute("SELECT 1 FROM patients WHERE phone = ?", (phone,)).fetchone():
                raise api_error(
                    409,
                    "phone_already_registered",
                    "This phone number is already registered. Log in, or ask the OPD desk for a one-time code if you have visited before.",
                )
            self._conn.execute(
                "INSERT INTO signup_codes (phone, name, age, code_hash, attempts, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, 0, ?, ?)"
                " ON CONFLICT(phone) DO UPDATE SET name = excluded.name, age = excluded.age,"
                " code_hash = excluded.code_hash, attempts = 0, created_at = excluded.created_at,"
                " expires_at = excluded.expires_at",
                (phone, _clean(name), age, _sha(f"{phone}:{code}"),
                 now.isoformat(timespec="microseconds"),
                 (now + timedelta(seconds=SIGNUP_CODE_SECONDS)).isoformat(timespec="microseconds")),
            )
        return code

    def signup_finish(self, phone: str, code: str, password: str) -> None:
        """Check the code, then create the patient record and their account together."""
        valid = taken = False
        with self._lock, self._conn:
            row = self._conn.execute("SELECT * FROM signup_codes WHERE phone = ?", (phone,)).fetchone()
            if row and row["expires_at"] > utc_now() and row["attempts"] < MAX_CODE_ATTEMPTS:
                if hmac.compare_digest(row["code_hash"], _sha(f"{phone}:{code}")):
                    valid = True
                else:
                    self._conn.execute("UPDATE signup_codes SET attempts = attempts + 1 WHERE phone = ?", (phone,))
            if valid:
                if self._conn.execute("SELECT 1 FROM patients WHERE phone = ?", (phone,)).fetchone():
                    taken = True  # the OPD desk registered this number while the patient was typing
                else:
                    now = utc_now()
                    self._conn.execute(
                        "INSERT INTO patients (phone, name, age, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (phone, row["name"], row["age"], now, now),
                    )
                    self._conn.execute(
                        "INSERT INTO patient_accounts (phone, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (phone, hash_password(password), now, now),
                    )
                self._conn.execute("DELETE FROM signup_codes WHERE phone = ?", (phone,))
        if not valid:
            raise api_error(401, "invalid_code", "That code is not valid or has expired. Please get a new one.")
        if taken:
            raise api_error(
                409,
                "phone_already_registered",
                "This phone number was just registered at the OPD desk. Ask them for a one-time code.",
            )

    def verify(self, phone: str, password: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT password_hash FROM patient_accounts WHERE phone = ?", (phone,)).fetchone()
        ok = check_password(password, row["password_hash"] if row else _DUMMY_HASH)
        return ok and row is not None

    def start_session(self, phone: str) -> tuple[str, datetime]:
        return self._sessions.start("patient", phone, PATIENT_SESSION_HOURS)

    def phone_from_session(self, token: str) -> str | None:
        return self._sessions.subject("patient", token)

    def logout(self, token: str) -> None:
        self._sessions.end(token)
