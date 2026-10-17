"""Administrator login, role-protected endpoints, the admin dashboard, and adding doctors, staff and stock."""

import pytest

from app.schemas.opd import Department
from app.services import accounts

ADMIN_ID, PASSWORD = "ADMIN-7", "a-long-password"


@pytest.fixture
def admin(opd):
    return opd.admins.add("Rohan Mehta", ADMIN_ID, PASSWORD)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth(anon, admin):
    return bearer(anon.post("/admin/login", json={"admin_id": ADMIN_ID, "password": PASSWORD}).json()["token"])


@pytest.fixture
def doctor_auth(anon, opd):
    opd.doctors.add("Dr. Asha Rao", "MH-1001", Department.general_medicine)
    return bearer(anon.post("/doctor/login", json={"name": "Dr. Asha Rao", "medical_id": "MH-1001"}).json()["token"])


@pytest.fixture
def staff_auth(anon, opd):
    opd.staff.add("Meena Joshi", "OPD-001")
    return bearer(anon.post("/staff/login", json={"name": "Meena Joshi", "staff_id": "OPD-001"}).json()["token"])


def register(client, phone="9876543210", department="general_medicine", headers=None):
    body = {"patient_name": "Asha Verma", "age": 34, "phone": phone, "department": department}
    return client.post("/opd/tokens", json=body, headers=headers)


# ---- Login -------------------------------------------------------------------------------

def test_admin_logs_in_with_id_and_password(anon, admin):
    response = anon.post("/admin/login", json={"admin_id": "admin-7", "password": PASSWORD})  # ID is not case sensitive
    assert response.status_code == 200
    body = response.json()
    assert body["admin"] == {"id": admin.id, "name": "Rohan Mehta", "admin_id": ADMIN_ID}
    assert len(body["token"]) > 30


@pytest.mark.parametrize("admin_id, password", [(ADMIN_ID, "wrong-password"), ("NOBODY-1", PASSWORD)])
def test_wrong_admin_credentials_give_the_same_error(anon, admin, admin_id, password):
    response = anon.post("/admin/login", json={"admin_id": admin_id, "password": password})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_admin_account_locks_after_five_wrong_passwords(anon, admin, opd):
    for _ in range(accounts.MAX_ADMIN_FAILURES):
        assert anon.post("/admin/login", json={"admin_id": ADMIN_ID, "password": "nope-nope"}).status_code == 401
    locked = anon.post("/admin/login", json={"admin_id": ADMIN_ID, "password": PASSWORD})  # even the right one
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "too_many_attempts"

    opd._conn.execute("UPDATE admins SET locked_until = '2000-01-01T00:00:00+00:00'")  # the lock runs out
    assert anon.post("/admin/login", json={"admin_id": ADMIN_ID, "password": PASSWORD}).status_code == 200


def test_a_good_login_resets_the_failure_count(anon, admin):
    for _ in range(accounts.MAX_ADMIN_FAILURES - 1):
        anon.post("/admin/login", json={"admin_id": ADMIN_ID, "password": "nope-nope"})
    assert anon.post("/admin/login", json={"admin_id": ADMIN_ID, "password": PASSWORD}).status_code == 200
    for _ in range(accounts.MAX_ADMIN_FAILURES - 1):
        assert anon.post("/admin/login", json={"admin_id": ADMIN_ID, "password": "nope-nope"}).status_code == 401


def test_admin_password_must_be_long_enough_and_id_unique(opd, admin):
    with pytest.raises(ValueError, match="at least 8"):
        opd.admins.add("Someone", "ADMIN-8", "short")
    with pytest.raises(ValueError, match="already registered"):
        opd.admins.add("Someone Else", "admin-7", "another-password")


def test_logout_ends_the_session(anon, admin_auth):
    assert anon.get("/admin/dashboard", headers=admin_auth).status_code == 200
    assert anon.post("/admin/logout", headers=admin_auth).status_code == 204
    assert anon.get("/admin/dashboard", headers=admin_auth).status_code == 401


# ---- Who may call what ---------------------------------------------------------------------

PROTECTED_FOR_ADMIN_ONLY = [
    ("get", "/admin/dashboard"),
    ("get", "/work-orders"),
    ("post", "/summarize"),
]


@pytest.mark.parametrize("method, path", PROTECTED_FOR_ADMIN_ONLY + [("get", "/opd/tokens"), ("get", "/opd/departments")])
def test_no_login_no_access(anon, method, path):
    response = getattr(anon, method)(path)
    assert response.status_code == 401 and response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.parametrize("method, path", PROTECTED_FOR_ADMIN_ONLY)
def test_only_the_admin_may_use_admin_endpoints(anon, doctor_auth, staff_auth, method, path):
    for headers in (doctor_auth, staff_auth):
        response = getattr(anon, method)(path, headers=headers)
        assert response.status_code == 403 and response.json()["error"]["code"] == "forbidden"


def test_a_patient_login_is_not_a_staff_login(anon):
    code = anon.post("/patient/signup/start", json={"phone": "9123456780", "name": "Pat Ient", "age": 30}).json()["code"]
    token = anon.post("/patient/signup", json={"phone": "9123456780", "code": code, "password": "a-good-password"})
    assert token.status_code == 200
    patient = bearer(token.json()["token"])
    assert anon.get("/opd/tokens", headers=patient).status_code == 403
    assert anon.get("/work-orders", headers=patient).status_code == 403


def test_garbage_token_is_session_expired(anon):
    response = anon.get("/opd/tokens", headers=bearer("not-a-real-token"))
    assert response.status_code == 401 and response.json()["error"]["code"] == "session_expired"


def test_staff_and_admin_run_the_queue(anon, staff_auth, admin_auth):
    assert register(anon, "9000000001", headers=staff_auth).status_code == 201
    assert register(anon, "9000000002", headers=admin_auth).status_code == 201
    assert len(anon.get("/opd/tokens", headers=staff_auth).json()) == 2
    assert anon.get("/opd/tokens/GM-001", headers=admin_auth).status_code == 200
    assert anon.get("/opd/departments", headers=staff_auth).status_code == 200


def test_doctor_cannot_register_or_list_but_can_move_own_departments_tokens(anon, staff_auth, doctor_auth):
    assert anon.get("/opd/tokens", headers=doctor_auth).status_code == 403
    assert register(anon, "9000000001", headers=doctor_auth).status_code == 403
    register(anon, "9000000001", headers=staff_auth)
    register(anon, "9000000002", department="cardiology", headers=staff_auth)

    own = anon.patch("/opd/tokens/GM-001/status", json={"status": "in_consultation"}, headers=doctor_auth)
    assert own.status_code == 200
    other = anon.patch("/opd/tokens/CD-001/status", json={"status": "in_consultation"}, headers=doctor_auth)
    assert other.status_code == 403 and other.json()["error"]["code"] == "wrong_department"
    assert anon.get("/opd/departments", headers=doctor_auth).status_code == 200


# ---- Dashboard -------------------------------------------------------------------------------

def test_dashboard_on_an_empty_hospital(anon, admin_auth):
    board = anon.get("/admin/dashboard", headers=admin_auth).json()
    assert board["admin"]["admin_id"] == ADMIN_ID
    assert board["today"] == {"registered": 0, "waiting": 0, "in_consultation": 0, "completed": 0, "cancelled": 0, "average_wait_minutes": None}
    assert board["totals"] == {"patients": 0, "visits": 0, "doctors": 0, "staff": 0}
    assert len(board["visits_last_7_days"]) == 7 and all(d["visits"] == 0 for d in board["visits_last_7_days"])
    assert len(board["departments"]) == len(Department)
    assert board["doctors"] == [] and board["recent_activity"] == []
    assert board["pharmacy"]["medicines"] == 0 and board["pharmacy"]["work_orders_by_status"] == {
        "requested": 0, "ordered": 0, "received": 0, "completed": 0}


def test_dashboard_shows_the_hospital_at_work(anon, supply, opd, staff_auth, doctor_auth, admin_auth):
    supply.add_stock("Paracetamol 500mg", 100)
    supply.add_stock("Insulin Glargine", 5)
    supply.add_stock("Amoxicillin 250mg", 0)
    paracetamol = anon.get("/doctor/medicines", params={"q": "para"}, headers=doctor_auth).json()[0]
    anon.post("/work-orders", headers=admin_auth, json={
        "medicine_name": "Insulin Glargine", "quantity_needed": 50, "priority": "critical", "description": "Shipment delayed for a week."})

    register(anon, "9000000001", headers=staff_auth)
    register(anon, "9000000002", headers=staff_auth)
    register(anon, "9000000003", department="cardiology", headers=staff_auth)
    first = "/opd/tokens/GM-001/status"
    anon.patch(first, json={"status": "in_consultation"}, headers=doctor_auth)
    anon.put("/doctor/consultations/GM-001", headers=doctor_auth, json={
        "remarks": "Viral fever", "prescription": [{"medicine_id": paracetamol["id"], "quantity": 10}]})
    for step in ("prescribed", "pharmacy", "completed"):
        anon.patch(first, json={"status": step}, headers=doctor_auth)
    anon.patch("/opd/tokens/GM-002/status", json={"status": "cancelled"}, headers=staff_auth)

    board = anon.get("/admin/dashboard", headers=admin_auth).json()

    assert board["today"]["registered"] == 3 and board["today"]["completed"] == 1 and board["today"]["cancelled"] == 1
    assert board["today"]["waiting"] == 1 and board["today"]["in_consultation"] == 0
    assert board["today"]["average_wait_minutes"] is not None and board["today"]["average_wait_minutes"] >= 0
    assert board["totals"] == {"patients": 3, "visits": 3, "doctors": 1, "staff": 1}
    assert board["visits_last_7_days"][-1]["visits"] == 3

    doctor = board["doctors"][0]
    assert doctor["name"] == "Dr. Asha Rao" and doctor["online"] is True
    assert (doctor["seen_today"], doctor["seen_total"], doctor["prescribed_today"]) == (1, 1, 1)
    assert doctor["waiting_in_department"] == 0 and doctor["last_active_at"]
    assert board["staff"][0]["staff_id"] == "OPD-001"

    pharmacy = board["pharmacy"]
    assert pharmacy["medicines"] == 3 and pharmacy["out_of_stock"] == 1
    assert [m["name"] for m in pharmacy["low_stock"]] == ["Amoxicillin 250mg", "Insulin Glargine"]
    assert pharmacy["dispensed_today"] == [{"medicine": "Paracetamol 500mg", "quantity": 10}]
    assert pharmacy["dispensed_today_units"] == 10
    assert pharmacy["open_work_orders"] == 1 and pharmacy["critical_open_work_orders"] == 1
    assert pharmacy["work_orders_by_status"]["requested"] == 1

    cardiology = next(d for d in board["departments"] if d["code"] == "cardiology")
    assert cardiology["waiting"] == 1
    texts = [e["text"] for e in board["recent_activity"]]
    assert any("Work order #1 for Insulin Glargine was raised" in t for t in texts)
    assert any("Token CD-001 was issued (Cardiology)" in t for t in texts)
    assert [e["at"] for e in board["recent_activity"]] == sorted((e["at"] for e in board["recent_activity"]), reverse=True)


def test_a_doctor_who_logs_out_is_offline(anon, doctor_auth, admin_auth):
    assert anon.get("/admin/dashboard", headers=admin_auth).json()["doctors"][0]["online"] is True
    anon.post("/doctor/logout", headers=doctor_auth)
    assert anon.get("/admin/dashboard", headers=admin_auth).json()["doctors"][0]["online"] is False


# ---- Adding people and stock -------------------------------------------------------------------

def test_admin_adds_a_doctor_who_can_then_log_in(anon, admin_auth):
    body = {"name": "Dr. Priya Menon", "medical_id": "MH-2002", "department": "ophthalmology"}
    created = anon.post("/admin/doctors", json=body, headers=admin_auth)
    assert created.status_code == 201
    assert created.json()["department_name"] == "Ophthalmology (Eye)"
    assert anon.post("/doctor/login", json={"name": "Dr. Priya Menon", "medical_id": "MH-2002"}).status_code == 200
    duplicate = anon.post("/admin/doctors", json={**body, "name": "Someone Else"}, headers=admin_auth)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "already_registered"


def test_admin_adds_staff_who_can_then_log_in(anon, admin_auth):
    created = anon.post("/admin/staff", json={"name": "Meena Joshi", "staff_id": "OPD-009"}, headers=admin_auth)
    assert created.status_code == 201
    assert anon.post("/staff/login", json={"name": "Meena Joshi", "staff_id": "OPD-009"}).status_code == 200
    assert anon.post("/admin/staff", json={"name": "Other", "staff_id": "opd-009"}, headers=admin_auth).status_code == 409


def test_admin_adds_stock_and_a_doctor_can_then_find_it(anon, supply, admin_auth, doctor_auth):
    first = anon.post("/admin/stock", json={"medicine": "  Cetirizine   10mg ", "quantity": 40}, headers=admin_auth)
    assert first.status_code == 201 and first.json()["name"] == "Cetirizine 10mg" and first.json()["stock"] == 40
    assert anon.post("/admin/stock", json={"medicine": "cetirizine 10mg", "quantity": 10}, headers=admin_auth).json()["stock"] == 50
    found = anon.get("/doctor/medicines", params={"q": "cetir"}, headers=doctor_auth).json()
    assert found[0]["stock"] == 50


def test_only_the_admin_may_add_people_or_stock(anon, doctor_auth, staff_auth):
    requests = [
        ("/admin/doctors", {"name": "Dr. X Y", "medical_id": "MH-9", "department": "ent"}),
        ("/admin/staff", {"name": "Some One", "staff_id": "OPD-5"}),
        ("/admin/stock", {"medicine": "Aspirin", "quantity": 5}),
    ]
    for path, body in requests:
        assert anon.post(path, json=body).status_code == 401
        for headers in (doctor_auth, staff_auth):
            assert anon.post(path, json=body, headers=headers).status_code == 403


@pytest.mark.parametrize("quantity", [0, -5, 1_000_001])
def test_stock_quantity_must_be_sensible(anon, admin_auth, quantity):
    assert anon.post("/admin/stock", json={"medicine": "Aspirin", "quantity": quantity}, headers=admin_auth).status_code == 422
