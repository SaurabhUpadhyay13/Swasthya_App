from fastapi import APIRouter, Depends, status

from app.errors import ErrorResponse
from app.schemas.work_orders import (
    WorkOrder,
    WorkOrderCreate,
    WorkOrderStatus,
    WorkOrderStatusUpdate,
)
from app.services.work_orders import WorkOrderStore, get_work_order_store

router = APIRouter(prefix="/work-orders", tags=["Medicine work orders"])

_not_found = {404: {"model": ErrorResponse, "description": "Work order not found"}}


@router.post("", response_model=WorkOrder, status_code=status.HTTP_201_CREATED)
def create_work_order(data: WorkOrderCreate, store: WorkOrderStore = Depends(get_work_order_store)):
    """Raise a replenishment work order after a stock-out. Starts as `requested`."""
    return store.create(data)


@router.get("", response_model=list[WorkOrder])
def list_work_orders(
    status: WorkOrderStatus | None = None, store: WorkOrderStore = Depends(get_work_order_store)
):
    """All work orders, newest first. Optionally filter by status."""
    return store.list_orders(status)


@router.get("/{work_order_id}", response_model=WorkOrder, responses=_not_found)
def get_work_order(work_order_id: int, store: WorkOrderStore = Depends(get_work_order_store)):
    return store.get(work_order_id)


@router.patch(
    "/{work_order_id}/status",
    response_model=WorkOrder,
    responses={**_not_found, 409: {"model": ErrorResponse, "description": "Invalid status transition"}},
)
def update_work_order_status(
    work_order_id: int, update: WorkOrderStatusUpdate, store: WorkOrderStore = Depends(get_work_order_store)
):
    """Move a work order one step forward: requested → ordered → received → completed."""
    return store.update_status(work_order_id, update.status)
