VALID = {
    "medicine_name": "Paracetamol 500mg",
    "quantity_needed": 500,
    "priority": "high",
    "description": "Pharmacy ran out; many fever prescriptions pending.",
}


def create(client, **overrides):
    return client.post("/work-orders", json={**VALID, **overrides})


def test_create_returns_requested_work_order(client):
    response = create(client)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["status"] == "requested"
    assert body["medicine_name"] == "Paracetamol 500mg"


def test_create_validation_error_is_structured(client):
    response = create(client, quantity_needed=0, description="short")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert {d["field"] for d in error["details"]} == {"quantity_needed", "description"}


def test_list_is_newest_first_and_filterable(client):
    create(client, medicine_name="Aspirin")
    create(client, medicine_name="Insulin")
    client.patch("/work-orders/1/status", json={"status": "ordered"})

    names = [o["medicine_name"] for o in client.get("/work-orders").json()]
    assert names == ["Insulin", "Aspirin"]

    ordered = client.get("/work-orders", params={"status": "ordered"}).json()
    assert [o["medicine_name"] for o in ordered] == ["Aspirin"]


def test_get_by_id_and_not_found(client):
    create(client)
    assert client.get("/work-orders/1").json()["id"] == 1

    response = client.get("/work-orders/99")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "work_order_not_found"


def test_status_moves_forward_through_full_workflow(client):
    create(client)
    for step in ["ordered", "received", "completed"]:
        response = client.patch("/work-orders/1/status", json={"status": step})
        assert response.status_code == 200
        assert response.json()["status"] == step


def test_status_cannot_skip_steps_or_go_back(client):
    create(client)
    skip = client.patch("/work-orders/1/status", json={"status": "received"})
    assert skip.status_code == 409
    assert skip.json()["error"]["code"] == "invalid_status_transition"
    assert "ordered" in skip.json()["error"]["message"]

    client.patch("/work-orders/1/status", json={"status": "ordered"})
    back = client.patch("/work-orders/1/status", json={"status": "requested"})
    assert back.status_code == 409


def test_completed_work_order_is_final(client):
    create(client)
    for step in ["ordered", "received", "completed"]:
        client.patch("/work-orders/1/status", json={"status": step})
    response = client.patch("/work-orders/1/status", json={"status": "completed"})
    assert response.status_code == 409


def test_invalid_status_value_is_rejected(client):
    create(client)
    response = client.patch("/work-orders/1/status", json={"status": "teleported"})
    assert response.status_code == 422
