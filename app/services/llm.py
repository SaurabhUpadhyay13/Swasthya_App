"""Thin client for Groq's OpenAI-compatible chat endpoint (plain httpx, no SDK)."""

import httpx

from app.config import Settings
from app.errors import api_error
from app.schemas.work_orders import WorkOrder

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You summarise medicine replenishment work orders for hospital pharmacy and operations staff. "
    "Reply with at most two plain sentences covering what is needed, how urgent it is, and why. "
    "Use only the facts provided. Do not give medical advice."
)


def summarize_work_order(order: WorkOrder, settings: Settings) -> str:
    if not settings.groq_api_key:
        raise api_error(503, "llm_not_configured", "GROQ_API_KEY is not set. Add it to your .env file.")

    payload = {
        "model": settings.groq_model,
        "temperature": 0.2,
        "max_tokens": 120,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Medicine: {order.medicine_name}\n"
                    f"Quantity needed: {order.quantity_needed}\n"
                    f"Priority: {order.priority.value}\n"
                    f"Status: {order.status.value}\n"
                    f"Description: {order.description}"
                ),
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    try:
        response = httpx.post(GROQ_URL, json=payload, headers=headers, timeout=settings.groq_timeout_seconds)
    except httpx.TimeoutException:
        raise api_error(504, "llm_timeout", "The summarisation service took too long to respond.") from None
    except httpx.HTTPError:
        raise api_error(502, "llm_unavailable", "Could not reach the summarisation service.") from None

    if response.status_code == 429:
        raise api_error(429, "llm_rate_limited", "Groq rate limit reached. Please retry in a moment.")
    if response.status_code >= 400:
        # Never forward the upstream body: it can echo request details.
        raise api_error(502, "llm_error", f"The summarisation service returned an error ({response.status_code}).")

    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError):
        raise api_error(502, "llm_bad_response", "The summarisation service returned an unexpected response.") from None
