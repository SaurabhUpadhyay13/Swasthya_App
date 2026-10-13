from pydantic import BaseModel, Field


class SummarizeRequest(BaseModel):
    work_order_id: int = Field(gt=0)


class SummarizeResponse(BaseModel):
    work_order_id: int
    summary: str
    model: str
