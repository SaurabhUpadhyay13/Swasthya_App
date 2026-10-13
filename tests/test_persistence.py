"""Data must survive a restart, and every step must be logged with an exact timestamp."""

import sqlite3
from datetime import datetime

from app.schemas.opd import Department, PatientRegistration, TokenStatus
from app.schemas.work_orders import Priority, WorkOrderCreate, WorkOrderStatus
from app.services.opd import OpdStore
from app.services.work_orders import WorkOrderStore


def rows(db_path, sql):
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def assert_utc_and_ordered(timestamps):
    parsed = [datetime.fromisoformat(t) for t in timestamps]
    assert all(p.utcoffset().total_seconds() == 0 for p in parsed)
    assert parsed == sorted(parsed)


def test_work_orders_survive_restart_and_log_every_step(tmp_path):
    db = tmp_path / "supply_chain.db"
    first = WorkOrderStore(db)
    order = first.create(
        WorkOrderCreate(
            medicine_name="Insulin", quantity_needed=40, priority=Priority.critical,
            description="Cold chain delayed; two days of stock left.",
        )
    )
    first.update_status(order.id, WorkOrderStatus.ordered)

    restarted = WorkOrderStore(db)  # a new server process opening the same file
    assert restarted.get(order.id).status == WorkOrderStatus.ordered
    assert restarted.create(
        WorkOrderCreate(medicine_name="Saline", quantity_needed=5, description="Routine restock for ward.")
    ).id == order.id + 1

    events = rows(db, "SELECT from_status, to_status, occurred_at FROM work_order_events WHERE work_order_id = 1 ORDER BY id")
    assert [(e[0], e[1]) for e in events] == [(None, "requested"), ("requested", "ordered")]
    assert_utc_and_ordered([e[2] for e in events])


def test_opd_tokens_survive_restart_and_log_every_step(tmp_path):
    db = tmp_path / "opd.db"
    first = OpdStore(db_path=db)
    token = first.register(
        PatientRegistration(patient_name="Asha Verma", age=34, phone="9876543210", department=Department.general_medicine)
    )
    first.update_status(token.token, TokenStatus.in_consultation)
    first.update_status(token.token, TokenStatus.prescribed)

    restarted = OpdStore(db_path=db)
    assert restarted.get("GM-001").status == TokenStatus.prescribed
    # The counter continues instead of starting again at 001
    second = restarted.register(
        PatientRegistration(patient_name="Ravi Kumar", age=58, phone="9876500002", department=Department.general_medicine)
    )
    assert second.token == "GM-002"
    assert second.position == 1

    events = rows(db, "SELECT token, from_status, to_status, occurred_at FROM opd_events WHERE token = 'GM-001' ORDER BY id")
    assert [(e[1], e[2]) for e in events] == [(None, "waiting"), ("waiting", "in_consultation"), ("in_consultation", "prescribed")]
    assert_utc_and_ordered([e[3] for e in events])


def test_event_dataset_holds_no_patient_identity(tmp_path):
    db = tmp_path / "opd.db"
    OpdStore(db_path=db).register(PatientRegistration(patient_name="Asha Verma", age=34, phone="9876543210", department=Department.cardiology))
    columns = {c[1] for c in rows(db, "PRAGMA table_info(opd_events)")}
    assert columns.isdisjoint({"patient_name", "phone", "age", "complaint"})
