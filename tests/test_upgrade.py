"""A database written by an earlier release must still open and work with the current code."""

import sqlite3

import pytest
from fastapi import HTTPException

from app.schemas.opd import Department, PatientRegistration, TokenStatus
from app.services.opd import OpdStore

# The shape of opd_tokens from the first persistent release: no unique rule on open visits.
LEGACY = """
CREATE TABLE opd_tokens (
    token TEXT PRIMARY KEY, department TEXT NOT NULL, sequence INTEGER NOT NULL, patient_name TEXT NOT NULL,
    age INTEGER NOT NULL, phone TEXT, complaint TEXT, status TEXT NOT NULL,
    registered_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE (department, sequence)
);
INSERT INTO opd_tokens VALUES ('GM-001', 'general_medicine', 1, 'Dup Patient', 40, '9876543210', NULL, 'waiting', '2026-01-01T09:00:00.000000+00:00', '2026-01-01T09:00:00.000000+00:00');
INSERT INTO opd_tokens VALUES ('CD-001', 'cardiology', 1, 'Dup Patient', 40, '9876543210', NULL, 'waiting', '2026-01-01T09:01:00.000000+00:00', '2026-01-01T09:01:00.000000+00:00');
INSERT INTO opd_tokens VALUES ('EN-001', 'ent', 1, 'Old Record', 60, NULL, NULL, 'waiting', '2026-01-01T09:02:00.000000+00:00', '2026-01-01T09:02:00.000000+00:00');
"""


@pytest.fixture
def legacy_db(tmp_path):
    path = tmp_path / "opd.db"
    connection = sqlite3.connect(path)
    connection.executescript(LEGACY)
    connection.commit()
    connection.close()
    return path


def test_old_database_with_duplicate_open_visits_still_opens(legacy_db):
    store = OpdStore(db_path=legacy_db)  # must not crash on the duplicates already stored
    assert [t.token for t in store.list_tokens()] == ["GM-001", "CD-001", "EN-001"]


def test_new_registrations_still_follow_the_rule_on_an_old_database(legacy_db):
    store = OpdStore(db_path=legacy_db)
    with pytest.raises(HTTPException) as refused:
        store.register(PatientRegistration(patient_name="Dup Patient", age=40, phone="9876543210", department=Department.ent))
    assert refused.value.detail["code"] == "already_in_queue"
    assert store.register(PatientRegistration(patient_name="New", age=30, phone="9000000001", department=Department.ent)).token == "EN-002"


def test_old_tokens_without_a_phone_number_keep_working(legacy_db):
    store = OpdStore(db_path=legacy_db)
    assert store.update_status("EN-001", TokenStatus.in_consultation).status == TokenStatus.in_consultation
