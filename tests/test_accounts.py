"""OPD staff login and dashboard, patient login and dashboard, and the one-time access code."""

import pytest

from app.schemas.opd import Department

PHONE = "9876543210"


@pytest.fixture
def staff(opd):
    return opd.staff.add("Meena Joshi", "OPD-001")


@pytest.fixture
def staff_auth(client, staff):
    token = client.post("/staff/login", json={"name": "Meena Joshi", "staff_id": "OPD-001"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def register(client, name="Asha Verma", phone=PHONE, department="general_medicine", complaint="Fever"):
    body = {"patient_name": name, "age": 34, "phone": phone, "department": department, "complaint": complaint}
    return client.post("/opd/tokens", json=body).json()["token"]


def move(client, token, *steps):
    for step in steps:
        assert client.patch(f"/opd/tokens/{token}/status", json={"status": step}).status_code == 200


def code_for(client, staff_auth, phone=PHONE):
    return client.post("/staff/patient-codes", headers=staff_auth, json={"phone": phone}).json()["code"]


@pytest.fixture
def patient_auth(client, staff_auth):
    """A registered patient who has activated their account."""
    register(client)
    body = {"phone": PHONE, "code": code_for(client, staff_auth), "password": "correct-horse"}
    token = client.post("/patient/activate", json=body).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ---- Staff login ---------------------------------------------------------------------

def test_staff_login_with_name_and_staff_id(client, staff):
    response = client.post("/staff/login", json={"name": "meena  joshi", "staff_id": "opd-001"})
    assert response.status_code == 200
    assert response.json()["staff"] == {"id": staff.id, "name": "Meena Joshi", "staff_id": "OPD-001"}


@pytest.mark.parametrize("name, staff_id", [("Meena Joshi", "WRONG"), ("Nobody", "OPD-001")])
def test_staff_wrong_credentials_give_the_same_error(client, staff, name, staff_id):
    response = client.post("/staff/login", json={"name": name, "staff_id": staff_id})
    assert response.status_code == 401
    assert response.json()["error"] == {"code": "invalid_credentials", "message": "Name or staff ID not recognised."}


def test_staff_endpoints_need_a_login(client, staff):
    assert client.get("/staff/dashboard").json()["error"]["code"] == "not_authenticated"
    bad = client.get("/staff/dashboard", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "session_expired"
    assert client.post("/staff/patient-codes", json={"phone": PHONE}).status_code == 401


def test_staff_logout_ends_the_session(client, staff_auth):
    assert client.get("/staff/dashboard", headers=staff_auth).status_code == 200
    assert client.post("/staff/logout", headers=staff_auth).status_code == 204
    assert client.get("/staff/dashboard", headers=staff_auth).status_code == 401


def test_expired_staff_session_is_rejected(client, opd, staff_auth):
    opd._conn.execute("UPDATE account_sessions SET expires_at = '2000-01-01T00:00:00.000000+00:00'")
    opd._conn.commit()
    assert client.get("/staff/dashboard", headers=staff_auth).status_code == 401


def test_duplicate_staff_id_cannot_be_registered(opd, staff):
    with pytest.raises(ValueError):
        opd.staff.add("Someone Else", "opd-001")


def test_a_doctor_or_patient_session_does_not_open_the_staff_dashboard(client, opd, patient_auth):
    opd.doctors.add("Dr. Asha Rao", "MH-1001", Department.general_medicine)
    doctor = client.post("/doctor/login", json={"name": "Dr. Asha Rao", "medical_id": "MH-1001"}).json()["token"]
    assert client.get("/staff/dashboard", headers={"Authorization": f"Bearer {doctor}"}).status_code == 401
    assert client.get("/staff/dashboard", headers=patient_auth).status_code == 401


# ---- Staff dashboard -----------------------------------------------------------------

def test_staff_dashboard_shows_live_numbers(client, supply, staff_auth):
    supply.add_stock("Paracetamol 500mg", 5)       # low
    supply.add_stock("Cetirizine 10mg", 500)       # fine
    first = register(client, "One", "9000000001")
    register(client, "Two", "9000000002")
    register(client, "Kid", "9000000003", department="pediatrics")
    move(client, first, "in_consultation")
    done = register(client, "Done", "9000000004", department="cardiology")
    move(client, done, "in_consultation", "prescribed", "pharmacy", "completed")
    client.post("/work-orders", json={"medicine_name": "Insulin", "quantity_needed": 50, "priority": "critical",
                                      "description": "Cold chain delayed; two days of stock left."})

    board = client.get("/staff/dashboard", headers=staff_auth).json()
    assert board["staff"]["name"] == "Meena Joshi"
    assert (board["waiting"], board["in_consultation"]) == (2, 1)
    assert (board["registered_today"], board["completed_today"]) == (4, 1)
    assert [m["name"] for m in board["low_stock"]] == ["Paracetamol 500mg"]
    assert (board["open_work_orders"], board["critical_open_work_orders"]) == (1, 1)
    general = next(d for d in board["departments"] if d["code"] == "general_medicine")
    assert (general["waiting"], general["now_serving"]) == (1, "GM-001")


def test_empty_hospital_dashboard_is_all_zeros(client, staff_auth):
    board = client.get("/staff/dashboard", headers=staff_auth).json()
    assert [board[k] for k in ("waiting", "in_consultation", "registered_today", "completed_today")] == [0, 0, 0, 0]
    assert board["low_stock"] == []


# ---- Access codes and patient activation -----------------------------------------------

def test_staff_issues_a_code_only_for_a_known_patient(client, staff_auth):
    missing = client.post("/staff/patient-codes", headers=staff_auth, json={"phone": PHONE})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "patient_not_found"

    register(client)
    issued = client.post("/staff/patient-codes", headers=staff_auth, json={"phone": PHONE}).json()
    assert issued["patient_name"] == "Asha Verma"
    assert len(issued["code"]) == 6 and issued["code"].isdigit()


def test_phone_must_be_ten_digits(client, staff_auth):
    assert client.post("/staff/patient-codes", headers=staff_auth, json={"phone": "12345"}).status_code == 422
    assert client.post("/patient/login", json={"phone": "abc", "password": "x"}).status_code == 422


def test_code_is_stored_hashed_and_works_once(client, opd, staff_auth):
    register(client)
    code = code_for(client, staff_auth)
    assert code not in opd._conn.execute("SELECT code_hash FROM access_codes").fetchone()[0]

    body = {"phone": PHONE, "code": code, "password": "correct-horse"}
    assert client.post("/patient/activate", json=body).status_code == 200
    again = client.post("/patient/activate", json=body)
    assert again.status_code == 401 and again.json()["error"]["code"] == "invalid_code"


def test_wrong_code_is_refused_and_locks_after_five_tries(client, staff_auth):
    register(client)
    code = code_for(client, staff_auth)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post("/patient/activate", json={"phone": PHONE, "code": wrong, "password": "correct-horse"}).status_code == 401
    # Even the right code is refused now: the desk must issue a new one
    assert client.post("/patient/activate", json={"phone": PHONE, "code": code, "password": "correct-horse"}).status_code == 401
    fresh = code_for(client, staff_auth)
    assert client.post("/patient/activate", json={"phone": PHONE, "code": fresh, "password": "correct-horse"}).status_code == 200


def test_expired_code_is_refused(client, opd, staff_auth):
    register(client)
    code = code_for(client, staff_auth)
    opd._conn.execute("UPDATE access_codes SET expires_at = '2000-01-01T00:00:00.000000+00:00'")
    opd._conn.commit()
    response = client.post("/patient/activate", json={"phone": PHONE, "code": code, "password": "correct-horse"})
    assert response.status_code == 401


def test_a_code_does_not_work_for_another_phone(client, staff_auth):
    register(client)
    register(client, "Other", "9111111111")
    code = code_for(client, staff_auth)
    response = client.post("/patient/activate", json={"phone": "9111111111", "code": code, "password": "correct-horse"})
    assert response.status_code == 401


def test_password_must_be_at_least_eight_characters(client, staff_auth):
    register(client)
    response = client.post("/patient/activate", json={"phone": PHONE, "code": code_for(client, staff_auth), "password": "short"})
    assert response.status_code == 422


# ---- Patient login and dashboard -------------------------------------------------------

def test_patient_logs_in_with_phone_and_password(client, patient_auth):
    ok = client.post("/patient/login", json={"phone": PHONE, "password": "correct-horse"})
    assert ok.status_code == 200
    assert ok.json()["patient"] == {"phone": PHONE, "name": "Asha Verma", "age": 34}


@pytest.mark.parametrize("phone, password", [(PHONE, "wrong-password"), ("9000000000", "correct-horse")])
def test_patient_wrong_credentials_give_the_same_error(client, patient_auth, phone, password):
    response = client.post("/patient/login", json={"phone": phone, "password": password})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_password_is_not_stored_in_plain_text(client, opd, patient_auth):
    stored = opd._conn.execute("SELECT password_hash FROM patient_accounts").fetchone()[0]
    assert "correct-horse" not in stored and "$" in stored


def test_registered_patient_without_a_password_cannot_log_in(client):
    register(client)
    assert client.post("/patient/login", json={"phone": PHONE, "password": "anything-at-all"}).status_code == 401


def test_a_new_code_resets_the_password(client, staff_auth, patient_auth):
    body = {"phone": PHONE, "code": code_for(client, staff_auth), "password": "brand-new-pass"}
    assert client.post("/patient/activate", json=body).status_code == 200
    assert client.post("/patient/login", json={"phone": PHONE, "password": "correct-horse"}).status_code == 401
    assert client.post("/patient/login", json={"phone": PHONE, "password": "brand-new-pass"}).status_code == 200


def test_patient_endpoints_need_a_login_and_logout_works(client, patient_auth, staff_auth):
    assert client.get("/patient/dashboard").status_code == 401
    assert client.get("/patient/dashboard", headers=staff_auth).status_code == 401  # a staff token is not a patient token
    assert client.get("/patient/dashboard", headers=patient_auth).status_code == 200
    assert client.post("/patient/logout", headers=patient_auth).status_code == 204
    assert client.get("/patient/dashboard", headers=patient_auth).status_code == 401


def test_patient_dashboard_shows_live_token_and_history(client, supply, opd, staff_auth):
    supply.add_stock("Paracetamol 500mg", 100)
    opd.doctors.add("Dr. Asha Rao", "MH-1001", Department.general_medicine)
    doctor = client.post("/doctor/login", json={"name": "Dr. Asha Rao", "medical_id": "MH-1001"}).json()["token"]
    doc = {"Authorization": f"Bearer {doctor}"}
    medicine_id = client.get("/doctor/medicines", params={"q": "para"}, headers=doc).json()[0]["id"]

    first = register(client, complaint="Fever for 3 days")
    move(client, first, "in_consultation")
    client.put(f"/doctor/consultations/{first}", headers=doc, json={
        "remarks": "Viral fever. Rest and fluids.", "prescription": [{"medicine_id": medicine_id, "quantity": 6}]})
    move(client, first, "prescribed", "pharmacy", "completed")
    register(client, "Someone Else", "9111111111")      # another patient's visit must never appear
    second = register(client, complaint="Fever again")

    body = {"phone": PHONE, "code": code_for(client, staff_auth), "password": "correct-horse"}
    token = client.post("/patient/activate", json=body).json()["token"]
    board = client.get("/patient/dashboard", headers={"Authorization": f"Bearer {token}"}).json()

    assert board["patient"]["name"] == "Asha Verma"
    assert board["current"]["token"] == second and board["current"]["status"] == "waiting"
    assert board["total_visits"] == 2
    assert [v["token"] for v in board["visits"]] == [first]
    visit = board["visits"][0]
    assert visit["remarks"] == "Viral fever. Rest and fluids."
    assert visit["doctor_name"] == "Dr. Asha Rao"
    assert visit["prescription"][0]["medicine_name"] == "Paracetamol 500mg"
    assert visit["prescription"][0]["dispensed_quantity"] == 6


def test_patient_with_no_open_visit_has_no_current_token(client, patient_auth):
    board = client.get("/patient/dashboard", headers=patient_auth).json()
    assert board["current"] is not None            # the token registered in the fixture is still waiting
    token = board["current"]["token"]
    move(client, token, "in_consultation", "prescribed", "pharmacy", "completed")
    board = client.get("/patient/dashboard", headers=patient_auth).json()
    assert board["current"] is None
    assert [v["token"] for v in board["visits"]] == [token]
