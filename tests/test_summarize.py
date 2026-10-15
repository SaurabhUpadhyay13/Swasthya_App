import httpx
import pytest

from app.config import Settings, get_settings
from app.main import app
from app.services import llm

ORDER = {
    "medicine_name": "Insulin Glargine",
    "quantity_needed": 120,
    "priority": "critical",
    "description": "Shipment delayed; only two days of stock left for diabetic outpatients.",
}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def order(client):
    client.post("/work-orders", json=ORDER)


def test_summarize_returns_llm_text_and_sends_key_from_settings(client, order, monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers)
        return FakeResponse(payload={"choices": [{"message": {"content": "  Urgent insulin restock.  "}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)

    response = client.post("/summarize", json={"work_order_id": 1})
    assert response.status_code == 200
    assert response.json()["summary"] == "Urgent insulin restock."
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert "Insulin Glargine" in captured["json"]["messages"][1]["content"]


def test_summarize_unknown_work_order(client):
    response = client.post("/summarize", json={"work_order_id": 42})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "work_order_not_found"


def test_summarize_without_api_key(client, order):
    app.dependency_overrides[get_settings] = lambda: Settings(nvidia_api_key=None, _env_file=None)
    response = client.post("/summarize", json={"work_order_id": 1})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_not_configured"


@pytest.mark.parametrize(
    "outcome, status, code",
    [
        (httpx.ReadTimeout("slow"), 504, "llm_timeout"),
        (httpx.ConnectError("down"), 502, "llm_unavailable"),
        (FakeResponse(429), 429, "llm_rate_limited"),
        (FakeResponse(500), 502, "llm_error"),
        (FakeResponse(200, {"unexpected": True}), 502, "llm_bad_response"),
        (FakeResponse(200, {"choices": [{"message": {"content": None}}]}), 502, "llm_bad_response"),
    ],
)
def test_summarize_upstream_failures_are_structured(client, order, monkeypatch, outcome, status, code):
    def fake_post(*args, **kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    response = client.post("/summarize", json={"work_order_id": 1})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
