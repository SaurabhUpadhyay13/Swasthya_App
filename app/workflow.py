"""Both work orders and OPD tokens move strictly forward, one step at a time."""

from enum import Enum

from app.errors import api_error


def ensure_next_step(current: Enum, target: Enum, flow: tuple[Enum, ...], entity: str) -> None:
    """Raise 409 unless `target` is the step right after `current` in `flow`."""
    position = flow.index(current)
    if position == len(flow) - 1:
        raise api_error(409, "invalid_status_transition", f"{entity} is already '{current.value}' and cannot change.")
    expected = flow[position + 1]
    if target != expected:
        raise api_error(
            409,
            "invalid_status_transition",
            f"Cannot move {entity} from '{current.value}' to '{target.value}'. "
            f"Next allowed status: '{expected.value}'.",
        )
