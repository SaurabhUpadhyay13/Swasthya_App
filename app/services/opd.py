"""OPD dataset, stored in SQLite (data/opd.db).

Tables:
  patients            one row per patient, keyed by phone number (the permanent patient ID)
  opd_tokens          one row per visit: the token, its department and its current status
  opd_events          one row for every step a token takes, with the exact UTC time.
                      This is the table to analyse (waiting time, consultation time, ...).
                      It deliberately holds no patient name or phone number.
  consultations       the doctor's remarks for a visit
  prescription_items  the medicines prescribed in a visit, and how many were dispensed
  doctors, doctor_sessions   see services/doctors.py
  staff, patient_accounts, access_codes, account_sessions   see services/accounts.py

A patient's visits are found through the phone number, because the token number
(GM-004) only identifies one visit.
"""

from pathlib import Path
from threading import RLock

from fastapi import Depends

from app.config import Settings, get_settings
from app.db import connect, utc_now
from app.errors import api_error
from app.schemas.accounts import PatientDashboard, PatientProfile
from app.schemas.doctors import Consultation, ConsultationSave, Doctor, PrescriptionItem, Visit
from app.schemas.opd import (
    DEPARTMENTS,
    TOKEN_FLOW,
    Department,
    DepartmentQueue,
    PatientRegistration,
    Token,
    TokenStatus,
)
from app.services.accounts import SCHEMA as ACCOUNT_SCHEMA
from app.services.accounts import PatientAccounts, Sessions, StaffStore
from app.services.doctors import SCHEMA as DOCTOR_SCHEMA
from app.services.doctors import DoctorStore
from app.services.work_orders import WorkOrderStore, get_work_order_store
from app.workflow import ensure_next_step

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    phone      TEXT    PRIMARY KEY,              -- 10 digits, the permanent patient ID
    name       TEXT    NOT NULL,
    age        INTEGER NOT NULL,
    created_at TEXT    NOT NULL,                 -- first registration, UTC
    updated_at TEXT    NOT NULL                  -- latest registration, UTC
);
CREATE TABLE IF NOT EXISTS opd_tokens (
    token         TEXT    PRIMARY KEY,           -- e.g. GM-004
    department    TEXT    NOT NULL,
    sequence      INTEGER NOT NULL,
    patient_name  TEXT    NOT NULL,
    age           INTEGER NOT NULL,
    phone         TEXT,                          -- links the visit to patients.phone
    complaint     TEXT,
    status        TEXT    NOT NULL,
    registered_at TEXT    NOT NULL,              -- UTC, microsecond precision
    updated_at    TEXT    NOT NULL,
    UNIQUE (department, sequence)
);
CREATE INDEX IF NOT EXISTS idx_opd_tokens_queue ON opd_tokens (department, status, sequence);
CREATE INDEX IF NOT EXISTS idx_opd_tokens_phone ON opd_tokens (phone);
CREATE TABLE IF NOT EXISTS opd_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    token       TEXT    NOT NULL REFERENCES opd_tokens(token),
    department  TEXT    NOT NULL,
    from_status TEXT,                            -- NULL means the token was just issued
    to_status   TEXT    NOT NULL,
    occurred_at TEXT    NOT NULL                 -- UTC, microsecond precision
);
CREATE INDEX IF NOT EXISTS idx_opd_events_token ON opd_events (token, occurred_at);
CREATE TABLE IF NOT EXISTS consultations (
    token      TEXT    PRIMARY KEY REFERENCES opd_tokens(token),
    doctor_id  INTEGER NOT NULL REFERENCES doctors(id),
    remarks    TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS prescription_items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    token              TEXT    NOT NULL REFERENCES opd_tokens(token),
    medicine_id        INTEGER NOT NULL,         -- medicines.id in supply_chain.db
    medicine_name      TEXT    NOT NULL,         -- name as it was when prescribed
    quantity           INTEGER NOT NULL,
    instructions       TEXT,
    prescribed_at      TEXT    NOT NULL,         -- UTC, microsecond precision
    dispensed_quantity INTEGER,                  -- NULL until the pharmacy completes the token
    dispensed_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_prescription_items_token ON prescription_items (token);
"""

_EVENT = "INSERT INTO opd_events (token, department, from_status, to_status, occurred_at) VALUES (?, ?, ?, ?, ?)"

# A token's place in line is computed in SQL: 1 + number of waiting tokens before it in the same department.
_SELECT_TOKEN = """
SELECT t.*,
       CASE WHEN t.status = 'waiting' THEN 1 + (
           SELECT COUNT(*) FROM opd_tokens a
           WHERE a.department = t.department AND a.status = 'waiting' AND a.sequence < t.sequence
       ) END AS position
FROM opd_tokens t
"""


class OpdStore:
    def __init__(
        self,
        avg_consult_minutes: int = 10,
        db_path: str | Path = ":memory:",
        supply: WorkOrderStore | None = None,
    ) -> None:
        """`supply` is the medicine stock; without it, completing a token does not touch stock."""
        self._avg_minutes = avg_consult_minutes
        self._supply = supply
        self._conn = connect(db_path)
        self._conn.executescript(DOCTOR_SCHEMA + SCHEMA + ACCOUNT_SCHEMA)
        self._lock = RLock()
        self.doctors = DoctorStore(self._conn, self._lock)
        sessions = Sessions(self._conn, self._lock)
        self.staff = StaffStore(self._conn, self._lock, sessions)
        self.patient_accounts = PatientAccounts(self._conn, self._lock, sessions)

    def _to_token(self, row) -> Token:
        values = dict(row)
        position = values.pop("position")
        return Token(
            **values,
            department_name=DEPARTMENTS[Department(values["department"])][0],
            position=position,
            estimated_wait_minutes=position * self._avg_minutes if position else None,
        )

    def _select(self, token_id: str) -> Token:
        row = self._conn.execute(_SELECT_TOKEN + " WHERE t.token = ?", (token_id.upper(),)).fetchone()
        if row is None:
            raise api_error(404, "token_not_found", f"Token '{token_id}' does not exist.")
        return self._to_token(row)

    # ---- Visits and the queue -----------------------------------------------------

    def register(self, data: PatientRegistration) -> Token:
        _, prefix = DEPARTMENTS[data.department]
        now = utc_now()
        with self._lock, self._conn:
            # New patient, or a returning one: the phone number decides. Latest name and age win.
            self._conn.execute(
                "INSERT INTO patients (phone, name, age, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(phone) DO UPDATE SET name = excluded.name, age = excluded.age,"
                " updated_at = excluded.updated_at",
                (data.phone, data.patient_name, data.age, now, now),
            )
            last = self._conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM opd_tokens WHERE department = ?", (data.department.value,)
            ).fetchone()[0]
            sequence = last + 1
            token = f"{prefix}-{sequence:03d}"
            self._conn.execute(
                "INSERT INTO opd_tokens (token, department, sequence, patient_name, age, phone, complaint, status, registered_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (token, data.department.value, sequence, data.patient_name, data.age, data.phone,
                 data.complaint, TokenStatus.waiting.value, now, now),
            )
            self._conn.execute(_EVENT, (token, data.department.value, None, TokenStatus.waiting.value, now))
            return self._select(token)

    def get(self, token_id: str) -> Token:
        with self._lock:
            return self._select(token_id)

    def list_tokens(self, department: Department | None = None, status: TokenStatus | None = None) -> list[Token]:
        conditions, params = [], []
        if department is not None:
            conditions.append("t.department = ?")
            params.append(department.value)
        if status is not None:
            conditions.append("t.status = ?")
            params.append(status.value)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        with self._lock:
            rows = self._conn.execute(
                _SELECT_TOKEN + where + " ORDER BY t.registered_at, t.sequence", params
            ).fetchall()
        return [self._to_token(row) for row in rows]

    def update_status(self, token_id: str, new_status: TokenStatus) -> Token:
        with self._lock, self._conn:
            token = self._select(token_id)
            ensure_next_step(token.status, new_status, TOKEN_FLOW, "token")
            if new_status == TokenStatus.in_consultation:
                busy = self._conn.execute(
                    "SELECT token FROM opd_tokens WHERE department = ? AND status = 'in_consultation'",
                    (token.department.value,),
                ).fetchone()
                if busy:
                    raise api_error(
                        409,
                        "doctor_busy",
                        f"Token {busy['token']} is still in consultation in {token.department_name}.",
                    )
            now = utc_now()
            if new_status == TokenStatus.completed:
                self._dispense(token.token, now)
            self._conn.execute(
                "UPDATE opd_tokens SET status = ?, updated_at = ? WHERE token = ?",
                (new_status.value, now, token.token),
            )
            self._conn.execute(
                _EVENT, (token.token, token.department.value, token.status.value, new_status.value, now)
            )
            return self._select(token.token)

    def _dispense(self, token: str, now: str) -> None:
        """The pharmacy hands over the prescribed medicines: take them from stock and record what was given.

        If stock is short, the patient gets what is available. The shortfall stays visible as
        dispensed_quantity < quantity, which is useful for analysis.
        """
        items = self._conn.execute(
            "SELECT id, medicine_id, quantity FROM prescription_items WHERE token = ?", (token,)
        ).fetchall()
        if not items or self._supply is None:
            return
        given = self._supply.dispense([(item["medicine_id"], item["quantity"]) for item in items])
        for item, taken in zip(items, given):
            self._conn.execute(
                "UPDATE prescription_items SET dispensed_quantity = ?, dispensed_at = ? WHERE id = ?",
                (taken, now, item["id"]),
            )

    def departments(self) -> list[DepartmentQueue]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT department,"
                "       SUM(status = 'waiting') AS waiting,"
                "       MAX(CASE WHEN status = 'in_consultation' THEN token END) AS serving"
                " FROM opd_tokens GROUP BY department"
            ).fetchall()
        stats = {row["department"]: row for row in rows}
        summary = []
        for code, (name, prefix) in DEPARTMENTS.items():
            row = stats.get(code.value)
            summary.append(
                DepartmentQueue(
                    code=code,
                    name=name,
                    prefix=prefix,
                    now_serving=row["serving"] if row else None,
                    waiting=row["waiting"] if row else 0,
                )
            )
        return summary

    # ---- OPD staff and patient dashboards -------------------------------------------------

    def day_stats(self, since: str) -> dict[str, int]:
        """Live counts for the OPD staff dashboard. `since` is the start of today, as a UTC timestamp."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(status = 'waiting'), 0) AS waiting,"
                "       COALESCE(SUM(status = 'in_consultation'), 0) AS in_consultation,"
                "       COALESCE(SUM(registered_at >= ?), 0) AS registered_today,"
                "       COALESCE(SUM(status = 'completed' AND updated_at >= ?), 0) AS completed_today"
                " FROM opd_tokens",
                (since, since),
            ).fetchone()
        return dict(row)

    def patient_dashboard(self, phone: str) -> PatientDashboard:
        """Everything one patient may see: their live token and their visit history (matched by phone)."""
        with self._lock:
            patient = self._conn.execute("SELECT phone, name, age FROM patients WHERE phone = ?", (phone,)).fetchone()
            if patient is None:
                raise api_error(404, "patient_not_found", "No patient record for this phone number.")
            active = self._conn.execute(
                "SELECT token FROM opd_tokens WHERE phone = ? AND status != 'completed'"
                " ORDER BY registered_at DESC LIMIT 1",
                (phone,),
            ).fetchone()
            current = self._select(active["token"]) if active else None
            visits = self._visits(phone, current.token if current else "")
            total = self._conn.execute("SELECT COUNT(*) FROM opd_tokens WHERE phone = ?", (phone,)).fetchone()[0]
        return PatientDashboard(patient=PatientProfile(**dict(patient)), current=current, visits=visits, total_visits=total)

    # ---- Doctor's consultation: remarks, prescription, earlier visits ------------------

    @staticmethod
    def _require_department(token: Token, doctor: Doctor) -> None:
        if token.department != doctor.department:
            raise api_error(
                403, "wrong_department", f"Token {token.token} belongs to {token.department_name}, not your department."
            )

    def _items(self, tokens: list[str]) -> dict[str, list[PrescriptionItem]]:
        if not tokens:
            return {}
        marks = ",".join("?" * len(tokens))
        rows = self._conn.execute(
            f"SELECT * FROM prescription_items WHERE token IN ({marks}) ORDER BY id", tokens
        ).fetchall()
        grouped: dict[str, list[PrescriptionItem]] = {}
        for row in rows:
            grouped.setdefault(row["token"], []).append(PrescriptionItem(**dict(row)))
        return grouped

    def _visits(self, phone: str | None, exclude_token: str) -> list[Visit]:
        """Every other visit of the same patient, newest first."""
        if not phone:
            return []
        rows = self._conn.execute(
            "SELECT t.token, t.department, t.registered_at, t.status, t.complaint, c.remarks, d.name AS doctor_name"
            " FROM opd_tokens t"
            " LEFT JOIN consultations c ON c.token = t.token"
            " LEFT JOIN doctors d ON d.id = c.doctor_id"
            " WHERE t.phone = ? AND t.token != ? ORDER BY t.registered_at DESC",
            (phone, exclude_token),
        ).fetchall()
        items = self._items([row["token"] for row in rows])
        return [
            Visit(
                **dict(row),
                department_name=DEPARTMENTS[Department(row["department"])][0],
                prescription=items.get(row["token"], []),
            )
            for row in rows
        ]

    def _consultation(self, token: Token) -> Consultation:
        phone = self._conn.execute("SELECT phone FROM opd_tokens WHERE token = ?", (token.token,)).fetchone()[0]
        saved = self._conn.execute("SELECT remarks FROM consultations WHERE token = ?", (token.token,)).fetchone()
        return Consultation(
            token=token,
            patient_phone=phone or "",
            remarks=saved["remarks"] if saved else "",
            prescription=self._items([token.token]).get(token.token, []),
            previous_visits=self._visits(phone, token.token),
        )

    def get_consultation(self, token_id: str, doctor: Doctor) -> Consultation:
        with self._lock:
            token = self._select(token_id)
            self._require_department(token, doctor)
            return self._consultation(token)

    def save_consultation(self, token_id: str, doctor: Doctor, body: ConsultationSave) -> Consultation:
        """Save the remarks and prescription. Allowed only while the patient is with the doctor."""
        ids = [line.medicine_id for line in body.prescription]
        names = self._supply.medicine_names(ids) if self._supply else {}
        unknown = [i for i in ids if i not in names]
        if unknown:
            raise api_error(422, "unknown_medicine", f"Medicine {unknown[0]} is not in the OPD medicine list.")

        now = utc_now()
        with self._lock, self._conn:
            token = self._select(token_id)
            self._require_department(token, doctor)
            if token.status != TokenStatus.in_consultation:
                raise api_error(
                    409,
                    "not_in_consultation",
                    "Remarks and prescription can only be saved while the patient is in consultation.",
                )
            self._conn.execute(
                "INSERT INTO consultations (token, doctor_id, remarks, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(token) DO UPDATE SET doctor_id = excluded.doctor_id, remarks = excluded.remarks,"
                " updated_at = excluded.updated_at",
                (token.token, doctor.id, body.remarks, now, now),
            )
            self._conn.execute("DELETE FROM prescription_items WHERE token = ?", (token.token,))
            for line in body.prescription:
                self._conn.execute(
                    "INSERT INTO prescription_items (token, medicine_id, medicine_name, quantity, instructions, prescribed_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (token.token, line.medicine_id, names[line.medicine_id], line.quantity, line.instructions, now),
                )
            return self._consultation(token)


_store: OpdStore | None = None


def get_opd_store(
    settings: Settings = Depends(get_settings),
    supply: WorkOrderStore = Depends(get_work_order_store),
) -> OpdStore:
    """FastAPI dependency (tests override it with a fresh in-memory store)."""
    global _store
    if _store is None:
        _store = OpdStore(settings.avg_consult_minutes, settings.data_dir / "opd.db", supply)
    return _store
