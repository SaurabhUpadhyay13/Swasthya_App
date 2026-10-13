def register(client, name="Asha Verma", department="general_medicine", **extra):
    body = {"patient_name": name, "age": 34, "phone": "9876543210", "department": department, **extra}
    return client.post("/opd/tokens", json=body)


def set_status(client, token, status):
    return client.patch(f"/opd/tokens/{token}/status", json={"status": status})


def test_register_issues_department_token(client):
    first = register(client)
    assert first.status_code == 201
    assert first.json()["token"] == "GM-001"
    assert first.json()["position"] == 1
    assert first.json()["estimated_wait_minutes"] == 10

    assert register(client, name="Ravi Kumar").json()["token"] == "GM-002"
    # Each department has its own counter
    assert register(client, department="cardiology").json()["token"] == "CD-001"


def test_registration_validation(client):
    response = register(client, name="A", phone="123")
    assert response.status_code == 422
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert fields == {"patient_name", "phone"}


def test_phone_is_required_and_must_be_ten_digits(client):
    no_phone = client.post("/opd/tokens", json={"patient_name": "Asha Verma", "age": 34, "department": "ent"})
    assert no_phone.status_code == 422
    assert [d["field"] for d in no_phone.json()["error"]["details"]] == ["phone"]

    for bad in ["+919876543210", "98765 43210", "987654321", "abcdefghij"]:
        assert register(client, phone=bad).status_code == 422, bad


def test_open_token_responses_do_not_expose_the_phone_number(client):
    assert "phone" not in register(client).json()
    assert "phone" not in client.get("/opd/tokens/GM-001").json()
    assert "phone" not in client.get("/opd/tokens").json()[0]


def test_unknown_department_rejected(client):
    assert register(client, department="dentistry").status_code == 422


def test_position_updates_as_patients_are_served(client):
    register(client, name="One")
    register(client, name="Two")
    register(client, name="Three")
    assert client.get("/opd/tokens/GM-003").json()["position"] == 3

    set_status(client, "GM-001", "in_consultation")
    assert client.get("/opd/tokens/GM-003").json()["position"] == 2
    assert client.get("/opd/tokens/GM-001").json()["position"] is None  # no longer waiting


def test_token_lookup_is_case_insensitive_and_404s(client):
    register(client)
    assert client.get("/opd/tokens/gm-001").status_code == 200
    response = client.get("/opd/tokens/GM-999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "token_not_found"


def test_now_serving_per_department(client):
    register(client, name="One")
    register(client, name="Two")
    register(client, name="Kid", department="pediatrics")
    set_status(client, "GM-001", "in_consultation")

    queues = {q["code"]: q for q in client.get("/opd/departments").json()}
    assert queues["general_medicine"]["now_serving"] == "GM-001"
    assert queues["general_medicine"]["waiting"] == 1
    assert queues["pediatrics"]["now_serving"] is None
    assert queues["pediatrics"]["waiting"] == 1


def test_one_patient_in_consultation_per_department(client):
    register(client, name="One")
    register(client, name="Two")
    set_status(client, "GM-001", "in_consultation")

    response = set_status(client, "GM-002", "in_consultation")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "doctor_busy"

    set_status(client, "GM-001", "prescribed")  # frees the doctor
    assert set_status(client, "GM-002", "in_consultation").status_code == 200


def test_full_patient_journey_and_no_skipping(client):
    register(client)
    assert set_status(client, "GM-001", "pharmacy").status_code == 409

    for step in ["in_consultation", "prescribed", "pharmacy", "completed"]:
        assert set_status(client, "GM-001", step).json()["status"] == step


def test_list_filters(client):
    register(client, name="One")
    register(client, name="Kid", department="pediatrics")
    set_status(client, "GM-001", "in_consultation")

    assert len(client.get("/opd/tokens").json()) == 2
    assert len(client.get("/opd/tokens", params={"department": "pediatrics"}).json()) == 1
    assert len(client.get("/opd/tokens", params={"status": "in_consultation"}).json()) == 1
