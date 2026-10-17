"""Medicine supply-chain dataset, stored in SQLite (data/supply_chain.db).

Tables:
  work_orders        the current state of every work order (one row each)
  work_order_events  one row for every status change, with the exact UTC time.
                     This is the table to analyse (e.g. time from ordered to received).
  medicines          the OPD medicine list with its current stock.
                     Stock goes up when a work order is marked received and down when
                     a patient's medicines are dispensed (see OpdStore.update_status).
"""

from pathlib import Path
from threading import RLock

from fastapi import Depends

from app.config import Settings, get_settings
from app.db import connect, utc_now
from app.errors import api_error
from app.schemas.medicines import Medicine
from app.schemas.work_orders import (
    WORK_ORDER_FLOW,
    WorkOrder,
    WorkOrderCreate,
    WorkOrderStatus,
)
from app.workflow import ensure_next_step

SCHEMA = """
CREATE TABLE IF NOT EXISTS work_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_name   TEXT    NOT NULL,
    quantity_needed INTEGER NOT NULL,
    priority        TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS work_order_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id   INTEGER NOT NULL REFERENCES work_orders(id),
    medicine_name   TEXT    NOT NULL,
    quantity_needed INTEGER NOT NULL,
    priority        TEXT    NOT NULL,
    from_status     TEXT,                -- NULL means the work order was just created
    to_status       TEXT    NOT NULL,
    occurred_at     TEXT    NOT NULL     -- UTC, microsecond precision
);
CREATE INDEX IF NOT EXISTS idx_wo_events_order ON work_order_events (work_order_id, occurred_at);
CREATE TABLE IF NOT EXISTS medicines (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    stock      INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    updated_at TEXT    NOT NULL
);
"""

_EVENT = """
INSERT INTO work_order_events
    (work_order_id, medicine_name, quantity_needed, priority, from_status, to_status, occurred_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


class WorkOrderStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = connect(db_path)
        self._conn.executescript(SCHEMA)
        self._lock = RLock()

    def _select(self, order_id: int) -> WorkOrder:
        row = self._conn.execute("SELECT * FROM work_orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise api_error(404, "work_order_not_found", f"Work order {order_id} does not exist.")
        return WorkOrder(**dict(row))

    def create(self, data: WorkOrderCreate) -> WorkOrder:
        now = utc_now()
        with self._lock, self._conn:  # one transaction: the order and its first event, or neither
            cursor = self._conn.execute(
                "INSERT INTO work_orders (medicine_name, quantity_needed, priority, description, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (data.medicine_name, data.quantity_needed, data.priority.value, data.description,
                 WorkOrderStatus.requested.value, now, now),
            )
            order_id = cursor.lastrowid
            self._conn.execute(
                _EVENT,
                (order_id, data.medicine_name, data.quantity_needed, data.priority.value,
                 None, WorkOrderStatus.requested.value, now),
            )
            return self._select(order_id)

    def list_orders(self, status: WorkOrderStatus | None = None) -> list[WorkOrder]:
        sql, params = "SELECT * FROM work_orders", ()
        if status is not None:
            sql, params = sql + " WHERE status = ?", (status.value,)
        with self._lock:
            rows = self._conn.execute(sql + " ORDER BY id DESC", params).fetchall()
        return [WorkOrder(**dict(row)) for row in rows]

    def get(self, order_id: int) -> WorkOrder:
        with self._lock:
            return self._select(order_id)

    def update_status(self, order_id: int, new_status: WorkOrderStatus) -> WorkOrder:
        with self._lock, self._conn:
            order = self._select(order_id)
            ensure_next_step(order.status, new_status, WORK_ORDER_FLOW, "work order")
            now = utc_now()
            self._conn.execute(
                "UPDATE work_orders SET status = ?, updated_at = ? WHERE id = ?",
                (new_status.value, now, order_id),
            )
            self._conn.execute(
                _EVENT,
                (order_id, order.medicine_name, order.quantity_needed, order.priority.value,
                 order.status.value, new_status.value, now),
            )
            if new_status == WorkOrderStatus.received:  # same transaction: stock rises or nothing changes
                self._add_stock(order.medicine_name, order.quantity_needed, now)
            return self._select(order_id)

    # ---- Medicine stock ---------------------------------------------------------

    def _add_stock(self, name: str, quantity: int, now: str) -> None:
        """Add stock, creating the medicine if it is new. Caller owns the transaction."""
        self._conn.execute(
            "INSERT INTO medicines (name, stock, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET stock = stock + excluded.stock, updated_at = excluded.updated_at",
            (" ".join(name.split()), quantity, now),
        )

    def add_stock(self, name: str, quantity: int) -> Medicine:
        """Opening balance or manual top-up (python -m app.cli add-stock, or the admin dashboard)."""
        with self._lock, self._conn:
            self._add_stock(name, quantity, utc_now())
            row = self._conn.execute(
                "SELECT id, name, stock FROM medicines WHERE name = ?", (" ".join(name.split()),)
            ).fetchone()
        return Medicine(**dict(row))

    def search_medicines(self, query: str, limit: int = 8) -> list[Medicine]:
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, stock FROM medicines WHERE name LIKE ? ESCAPE '\\' ORDER BY name LIMIT ?",
                (f"%{escaped}%", limit),
            ).fetchall()
        return [Medicine(**dict(row)) for row in rows]

    def low_stock(self, level: int) -> list[Medicine]:
        """Medicines at or below `level`, lowest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, stock FROM medicines WHERE stock <= ? ORDER BY stock, name", (level,)
            ).fetchall()
        return [Medicine(**dict(row)) for row in rows]

    def stock_summary(self, low_level: int) -> dict:
        """Counts for the admin dashboard: how many medicines, how many are out, and the open work orders by status."""
        with self._lock:
            medicines, out = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(stock = 0), 0) FROM medicines"
            ).fetchone()
            by_status = {
                row["status"]: row["n"]
                for row in self._conn.execute("SELECT status, COUNT(*) AS n FROM work_orders GROUP BY status")
            }
            critical = self._conn.execute(
                "SELECT COUNT(*) FROM work_orders WHERE priority = 'critical' AND status IN ('requested', 'ordered')"
            ).fetchone()[0]
            events = self._conn.execute(
                "SELECT work_order_id, medicine_name, from_status, to_status, occurred_at"
                " FROM work_order_events ORDER BY id DESC LIMIT 10"
            ).fetchall()
        return {
            "medicines": medicines,
            "out_of_stock": out,
            "low_stock": self.low_stock(low_level)[:8],
            "by_status": {s.value: by_status.get(s.value, 0) for s in WorkOrderStatus},
            "critical_open": critical,
            "events": [dict(e) for e in events],
        }

    def medicine_names(self, ids: list[int]) -> dict[int, str]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        with self._lock:
            rows = self._conn.execute(f"SELECT id, name FROM medicines WHERE id IN ({marks})", ids).fetchall()
        return {row["id"]: row["name"] for row in rows}

    def dispense(self, lines: list[tuple[int, int]]) -> list[int]:
        """Take stock for (medicine_id, wanted) lines. Never goes below zero.

        Returns how many of each were actually available and taken, in the same order.
        """
        now = utc_now()
        given = []
        with self._lock, self._conn:
            for medicine_id, wanted in lines:
                row = self._conn.execute("SELECT stock FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
                taken = min(wanted, row["stock"]) if row else 0
                if taken:
                    self._conn.execute(
                        "UPDATE medicines SET stock = stock - ?, updated_at = ? WHERE id = ?",
                        (taken, now, medicine_id),
                    )
                given.append(taken)
        return given


_store: WorkOrderStore | None = None


def get_work_order_store(settings: Settings = Depends(get_settings)) -> WorkOrderStore:
    """FastAPI dependency (tests override it with a fresh in-memory store)."""
    global _store
    if _store is None:
        _store = WorkOrderStore(settings.data_dir / "supply_chain.db")
    return _store
