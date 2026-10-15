"""Thin client for NVIDIA's OpenAI-compatible chat endpoint (plain httpx, no SDK)."""

import httpx

from app.config import Settings
from app.errors import api_error
from app.schemas.work_orders import WorkOrder

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

SYSTEM_PROMPT = (
    "You summarise medicine replenishment work orders for hospital pharmacy and operations staff. "
    "Reply with at most two plain sentences covering what is needed, how urgent it is, and why. "
    "Use only the facts provided. Do not give medical advice."
)


def summarize_work_order(order: WorkOrder, settings: Settings) -> str:
    if not settings.nvidia_api_key:
        raise api_error(503, "llm_not_configured", "NVIDIA_API_KEY is not set. Add it to your .env file.")

    payload = {
        "model": settings.nvidia_model,
        "temperature": 0.2,
        # Reasoning models spend part of this budget thinking before they answer, so keep it generous.
        "max_tokens": 1024,
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
    headers = {"Authorization": f"Bearer {settings.nvidia_api_key}"}

    try:
        response = httpx.post(NVIDIA_URL, json=payload, headers=headers, timeout=settings.llm_timeout_seconds)
    except httpx.TimeoutException:
        raise api_error(504, "llm_timeout", "The summarisation service took too long to respond.") from None
    except httpx.HTTPError:
        raise api_error(502, "llm_unavailable", "Could not reach the summarisation service.") from None

    if response.status_code == 429:
        raise api_error(429, "llm_rate_limited", "NVIDIA rate limit reached. Please retry in a moment.")
    if response.status_code in (401, 403):
        raise api_error(
            502,
            "llm_not_authorised",
            "NVIDIA refused the request. Check NVIDIA_API_KEY in .env, and open the model's page on "
            "build.nvidia.com and click 'Try API' once to enable it.",
        )
    if response.status_code == 404:
        raise api_error(502, "llm_model_not_found", "NVIDIA does not know this model. Check NVIDIA_MODEL in .env.")
    if response.status_code >= 400:
        # Never forward the upstream body: it can echo request details.
        raise api_error(502, "llm_error", f"The summarisation service returned an error ({response.status_code}).")

    try:
        summary = (response.json()["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, ValueError):
        summary = ""
    if not summary:  # also covers a reasoning model that ran out of tokens before answering
        raise api_error(502, "llm_bad_response", "The summarisation service returned an unexpected response.")
    return summary
