from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class WorkOrderStatus(str, Enum):
    requested = "requested"
    ordered = "ordered"
    received = "received"
    completed = "completed"


# The only allowed path: Requested -> Ordered -> Received -> Completed
WORK_ORDER_FLOW = (
    WorkOrderStatus.requested,
    WorkOrderStatus.ordered,
    WorkOrderStatus.received,
    WorkOrderStatus.completed,
)


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class WorkOrderCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    medicine_name: str = Field(min_length=2, max_length=120, examples=["Paracetamol 500mg"])
    quantity_needed: int = Field(gt=0, le=100_000, examples=[500])
    priority: Priority = Priority.medium
    description: str = Field(
        min_length=10,
        max_length=2000,
        description="Why the stock is needed (e.g. what triggered the stock-out).",
        examples=["Pharmacy ran out this morning; 40 OPD prescriptions pending for fever cases."],
    )


class WorkOrderStatusUpdate(BaseModel):
    status: WorkOrderStatus


class WorkOrder(WorkOrderCreate):
    id: int
    status: WorkOrderStatus = WorkOrderStatus.requested
    created_at: datetime
    updated_at: datetime
