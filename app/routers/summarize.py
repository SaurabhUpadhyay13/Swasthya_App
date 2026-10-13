from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.errors import ErrorResponse
from app.schemas.summarize import SummarizeRequest, SummarizeResponse
from app.services.llm import summarize_work_order
from app.services.work_orders import WorkOrderStore, get_work_order_store

router = APIRouter(tags=["AI summary"])


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Work order not found"},
        503: {"model": ErrorResponse, "description": "GROQ_API_KEY not configured"},
        502: {"model": ErrorResponse, "description": "LLM provider error"},
    },
)
def summarize(
    request: SummarizeRequest,
    store: WorkOrderStore = Depends(get_work_order_store),
    settings: Settings = Depends(get_settings),
):
    """Summarise a work order's description with an LLM (Groq)."""
    order = store.get(request.work_order_id)
    summary = summarize_work_order(order, settings)
    return SummarizeResponse(work_order_id=order.id, summary=summary, model=settings.groq_model)
