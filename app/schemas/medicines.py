from pydantic import BaseModel


class Medicine(BaseModel):
    id: int
    name: str
    stock: int
