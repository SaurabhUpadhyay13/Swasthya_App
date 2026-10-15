import itertools

_phones = itertools.count(9000000001)  # every patient gets their own phone, as in real life


def register(client, name="Asha Verma", department="general_medicine", **extra):
    body = {"patient_name": name, "age": 34, "phone": str(next(_phones)), "department": department, **extra}
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
    assert register(client, department="astrology").status_code == 422


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


# ---- One open visit per patient, and cancelling ---------------------------------------------

def same_patient(client, department="general_medicine", phone="9876543210"):
    body = {"patient_name": "Asha Verma", "age": 34, "phone": phone, "department": department}
    return client.post("/opd/tokens", json=body)


def test_patient_cannot_hold_two_tokens_at_once(client):
    first = same_patient(client)
    assert first.status_code == 201

    for department in ("general_medicine", "cardiology"):  # same department or another one
        again = same_patient(client, department)
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "already_in_queue"
        assert "GM-001" in again.json()["error"]["message"]
    assert len(client.get("/opd/tokens").json()) == 1  # nothing extra was created


def test_a_second_token_is_allowed_after_completion(client):
    same_patient(client)
    for step in ["in_consultation", "prescribed", "pharmacy"]:
        set_status(client, "GM-001", step)
        assert same_patient(client, "cardiology").status_code == 409  # still open at every step
    set_status(client, "GM-001", "completed")
    assert same_patient(client, "cardiology").json()["token"] == "CD-001"


def test_cancelling_a_waiting_token_frees_the_patient(client):
    same_patient(client)
    cancelled = set_status(client, "GM-001", "cancelled")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["position"] is None
    assert same_patient(client, "cardiology").status_code == 201


def test_cancelled_token_leaves_the_queue(client):
    register(client, name="One")
    register(client, name="Two")
    set_status(client, "GM-001", "cancelled")
    assert client.get("/opd/tokens/GM-002").json()["position"] == 1
    assert {q["code"]: q["waiting"] for q in client.get("/opd/departments").json()}["general_medicine"] == 1


def test_only_a_waiting_token_can_be_cancelled_and_cancelled_is_final(client):
    register(client)
    set_status(client, "GM-001", "in_consultation")
    refused = set_status(client, "GM-001", "cancelled")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "invalid_status_transition"

    register(client, name="Other")
    set_status(client, "GM-002", "cancelled")
    for step in ["in_consultation", "cancelled"]:
        assert set_status(client, "GM-002", step).status_code == 409


def test_database_refuses_two_open_visits_even_if_the_app_check_is_skipped(client, opd):
    import sqlite3

    import pytest

    same_patient(client)
    with pytest.raises(sqlite3.IntegrityError):
        opd._conn.execute(
            "INSERT INTO opd_tokens (token, department, sequence, patient_name, age, phone, status, registered_at, updated_at)"
            " VALUES ('XX-001', 'ent', 1, 'Dup', 30, '9876543210', 'waiting', 'now', 'now')"
        )


def test_simultaneous_registrations_of_one_patient_create_exactly_one_token(opd):
    """Staff and patient press the button at the same moment, in different departments."""
    import threading

    from fastapi import HTTPException

    from app.schemas.opd import Department, PatientRegistration

    results = []

    def attempt(department):
        try:
            opd.register(PatientRegistration(patient_name="Asha Verma", age=34, phone="9876543210", department=department))
            results.append("ok")
        except HTTPException as error:
            results.append(error.detail["code"])

    departments = list(Department) * 4
    threads = [threading.Thread(target=attempt, args=(d,)) for d in departments]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 1
    assert results.count("already_in_queue") == len(departments) - 1
    assert len(opd.list_tokens()) == 1
