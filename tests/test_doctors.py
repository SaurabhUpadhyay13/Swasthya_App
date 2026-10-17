"""Doctor login, dashboard, remarks, prescribing, stock, and a patient's history across visits."""

import pytest

from app.schemas.opd import Department


@pytest.fixture
def doctor(opd):
    return opd.doctors.add("Dr. Asha Rao", "MH-1001", Department.general_medicine)


@pytest.fixture
def auth(client, doctor):
    token = client.post("/doctor/login", json={"name": "Dr. Asha Rao", "medical_id": "MH-1001"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def register(client, name="Asha Verma", phone="9876543210", department="general_medicine", complaint="Fever"):
    body = {"patient_name": name, "age": 34, "phone": phone, "department": department, "complaint": complaint}
    return client.post("/opd/tokens", json=body).json()["token"]


def move(client, token, *steps):
    for step in steps:
        assert client.patch(f"/opd/tokens/{token}/status", json={"status": step}).status_code == 200


def save(client, auth, token, remarks="Viral fever", lines=()):
    return client.put(f"/doctor/consultations/{token}", headers=auth, json={"remarks": remarks, "prescription": list(lines)})


# ---- Login and sessions ------------------------------------------------------------

def test_login_with_name_and_medical_id(client, doctor):
    response = client.post("/doctor/login", json={"name": "dr.  asha rao", "medical_id": "mh-1001"})
    assert response.status_code == 200
    body = response.json()
    assert body["doctor"]["name"] == "Dr. Asha Rao"
    assert body["doctor"]["department"] == "general_medicine"
    assert len(body["token"]) > 30


@pytest.mark.parametrize("name, medical_id", [("Dr. Asha Rao", "WRONG-ID"), ("Dr. Nobody", "MH-1001")])
def test_wrong_credentials_give_the_same_error(client, doctor, name, medical_id):
    response = client.post("/doctor/login", json={"name": name, "medical_id": medical_id})
    assert response.status_code == 401
    assert response.json()["error"] == {"code": "invalid_credentials", "message": "Name or medical ID not recognised."}


def test_doctor_endpoints_need_a_login(client, anon, doctor):
    missing = anon.get("/doctor/dashboard")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "not_authenticated"

    fake = client.get("/doctor/dashboard", headers={"Authorization": "Bearer not-a-real-token"})
    assert fake.status_code == 401
    assert fake.json()["error"]["code"] == "session_expired"


def test_logout_ends_the_session(client, auth):
    assert client.get("/doctor/dashboard", headers=auth).status_code == 200
    assert client.post("/doctor/logout", headers=auth).status_code == 204
    assert client.get("/doctor/dashboard", headers=auth).status_code == 401


def test_expired_session_is_rejected(client, opd, auth):
    opd._conn.execute("UPDATE doctor_sessions SET expires_at = '2000-01-01T00:00:00.000000+00:00'")
    opd._conn.commit()
    assert client.get("/doctor/dashboard", headers=auth).status_code == 401


def test_session_token_is_not_stored_in_plain_text(client, opd, doctor):
    token = client.post("/doctor/login", json={"name": "Dr. Asha Rao", "medical_id": "MH-1001"}).json()["token"]
    stored = [row[0] for row in opd._conn.execute("SELECT token_hash FROM doctor_sessions")]
    assert token not in stored


def test_duplicate_medical_id_cannot_be_registered(opd, doctor):
    with pytest.raises(ValueError):
        opd.doctors.add("Someone Else", "mh-1001", Department.cardiology)


# ---- Dashboard ---------------------------------------------------------------------

def test_dashboard_counts_only_the_doctors_own_department(client, auth):
    first = register(client, "One", "9000000001")
    register(client, "Two", "9000000002")
    register(client, "Kid", "9000000003", department="pediatrics")

    board = client.get("/doctor/dashboard", headers=auth).json()
    assert board["waiting"] == 2
    assert [t["token"] for t in board["queue"]] == ["GM-001", "GM-002"]
    assert board["current"] is None

    move(client, first, "in_consultation")
    board = client.get("/doctor/dashboard", headers=auth).json()
    assert board["waiting"] == 1
    assert board["current"]["token"] == "GM-001"


# ---- Remarks and prescribing ---------------------------------------------------------

def test_remarks_and_prescription_are_saved_while_in_consultation(client, supply, auth):
    supply.add_stock("Paracetamol 500mg", 100)
    medicine = client.get("/doctor/medicines", params={"q": "para"}, headers=auth).json()[0]
    token = register(client)
    move(client, token, "in_consultation")

    response = save(client, auth, token, "Fever 3 days. Advised rest.",
                    [{"medicine_id": medicine["id"], "quantity": 10, "instructions": "1 tablet twice a day"}])
    assert response.status_code == 200
    body = response.json()
    assert body["remarks"] == "Fever 3 days. Advised rest."
    assert body["prescription"][0]["medicine_name"] == "Paracetamol 500mg"
    assert body["prescription"][0]["dispensed_quantity"] is None

    # Saving again replaces the earlier prescription
    save(client, auth, token, "Updated", [])
    again = client.get(f"/doctor/consultations/{token}", headers=auth).json()
    assert again["remarks"] == "Updated"
    assert again["prescription"] == []


def test_cannot_save_unless_patient_is_in_consultation(client, auth):
    token = register(client)
    waiting = save(client, auth, token)
    assert waiting.status_code == 409
    assert waiting.json()["error"]["code"] == "not_in_consultation"

    move(client, token, "in_consultation", "prescribed")
    assert save(client, auth, token).status_code == 409  # locked once the doctor has finished


def test_doctor_cannot_open_another_departments_patient(client, auth):
    kid = register(client, "Kid", "9000000003", department="pediatrics")
    move(client, kid, "in_consultation")
    for response in (client.get(f"/doctor/consultations/{kid}", headers=auth), save(client, auth, kid)):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "wrong_department"


def test_prescription_must_use_known_medicines_once_each(client, supply, auth):
    supply.add_stock("Cetirizine 10mg", 5)
    medicine_id = client.get("/doctor/medicines", params={"q": "cet"}, headers=auth).json()[0]["id"]
    token = register(client)
    move(client, token, "in_consultation")

    unknown = save(client, auth, token, lines=[{"medicine_id": 999, "quantity": 1}])
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_medicine"

    line = {"medicine_id": medicine_id, "quantity": 1}
    twice = save(client, auth, token, lines=[line, line])
    assert twice.status_code == 422
    assert twice.json()["error"]["code"] == "validation_error"


# ---- Patient history, matched by phone number ---------------------------------------------

def test_second_visit_shows_the_first_visit_remarks(client, supply, auth):
    supply.add_stock("Paracetamol 500mg", 100)
    medicine_id = client.get("/doctor/medicines", params={"q": "para"}, headers=auth).json()[0]["id"]

    first = register(client, complaint="Fever for 3 days")
    move(client, first, "in_consultation")
    save(client, auth, first, "Viral fever. Rest and fluids.", [{"medicine_id": medicine_id, "quantity": 6}])
    move(client, first, "prescribed", "pharmacy", "completed")

    register(client, "Someone Else", "9111111111")  # a different patient must not appear in the history
    second = register(client, complaint="Fever again")
    move(client, "GM-002", "in_consultation", "prescribed")  # clear the doctor for the returning patient
    move(client, second, "in_consultation")

    visits = client.get(f"/doctor/consultations/{second}", headers=auth).json()["previous_visits"]
    assert [v["token"] for v in visits] == [first]
    visit = visits[0]
    assert visit["remarks"] == "Viral fever. Rest and fluids."
    assert visit["complaint"] == "Fever for 3 days"
    assert visit["doctor_name"] == "Dr. Asha Rao"
    assert visit["prescription"][0]["medicine_name"] == "Paracetamol 500mg"
    assert visit["prescription"][0]["dispensed_quantity"] == 6


def test_patient_row_is_created_once_per_phone(client, opd):
    first = register(client, "Asha Verma", "9876543210")
    move(client, first, "in_consultation", "prescribed", "pharmacy", "completed")
    register(client, "Asha V.", "9876543210")  # same phone, same patient (the first visit is finished)
    rows = opd._conn.execute("SELECT phone, name FROM patients").fetchall()
    assert [tuple(r) for r in rows] == [("9876543210", "Asha V.")]  # latest name wins
    assert opd._conn.execute("SELECT COUNT(*) FROM opd_tokens WHERE phone = '9876543210'").fetchone()[0] == 2


# ---- Medicine stock ----------------------------------------------------------------------

def test_medicine_search_shows_live_stock(client, supply, auth):
    supply.add_stock("Paracetamol 500mg", 40)
    supply.add_stock("Paracetamol 650mg", 0)
    supply.add_stock("Cetirizine 10mg", 7)

    found = client.get("/doctor/medicines", params={"q": "PARA"}, headers=auth).json()
    assert [(m["name"], m["stock"]) for m in found] == [("Paracetamol 500mg", 40), ("Paracetamol 650mg", 0)]
    assert client.get("/doctor/medicines", params={"q": "zzz"}, headers=auth).json() == []
    assert client.get("/doctor/medicines", params={"q": "%"}, headers=auth).json() == []  # not a wildcard
    assert client.get("/doctor/medicines", params={"q": "para"}).status_code == 401


def test_receiving_a_work_order_adds_stock(client, auth):
    order = client.post("/work-orders", json={
        "medicine_name": "paracetamol 500mg", "quantity_needed": 300, "priority": "high",
        "description": "Pharmacy ran out; many fever cases pending."}).json()
    for step in ["ordered", "received"]:
        client.patch(f"/work-orders/{order['id']}/status", json={"status": step})

    found = client.get("/doctor/medicines", params={"q": "paracetamol"}, headers=auth).json()
    assert [(m["name"], m["stock"]) for m in found] == [("paracetamol 500mg", 300)]

    # A second receipt for the same medicine (any capitalisation) adds to the same row
    again = client.post("/work-orders", json={
        "medicine_name": "Paracetamol 500mg", "quantity_needed": 50, "priority": "low",
        "description": "Small top-up for the weekend rush."}).json()
    for step in ["ordered", "received"]:
        client.patch(f"/work-orders/{again['id']}/status", json={"status": step})
    assert client.get("/doctor/medicines", params={"q": "paracetamol"}, headers=auth).json()[0]["stock"] == 350


def test_completing_a_token_dispenses_and_lowers_stock(client, supply, auth):
    supply.add_stock("Paracetamol 500mg", 8)
    supply.add_stock("Cetirizine 10mg", 100)
    ids = {m["name"]: m["id"] for q in ("para", "cet") for m in client.get("/doctor/medicines", params={"q": q}, headers=auth).json()}

    token = register(client)
    move(client, token, "in_consultation")
    save(client, auth, token, "Fever and allergy", [
        {"medicine_id": ids["Paracetamol 500mg"], "quantity": 10},   # only 8 in stock
        {"medicine_id": ids["Cetirizine 10mg"], "quantity": 5},
    ])
    move(client, token, "prescribed", "pharmacy")
    assert client.get("/doctor/medicines", params={"q": "para"}, headers=auth).json()[0]["stock"] == 8  # not yet handed over

    move(client, token, "completed")
    stock = {m["name"]: m["stock"] for q in ("para", "cet") for m in client.get("/doctor/medicines", params={"q": q}, headers=auth).json()}
    assert stock == {"Paracetamol 500mg": 0, "Cetirizine 10mg": 95}

    items = client.get(f"/doctor/consultations/{token}", headers=auth).json()["prescription"]
    given = {i["medicine_name"]: (i["quantity"], i["dispensed_quantity"]) for i in items}
    assert given == {"Paracetamol 500mg": (10, 8), "Cetirizine 10mg": (5, 5)}  # the shortfall is on record
    assert all(i["dispensed_at"] for i in items)
