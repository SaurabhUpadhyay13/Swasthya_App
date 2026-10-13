from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Department(str, Enum):
    general_medicine = "general_medicine"
    pediatrics = "pediatrics"
    orthopedics = "orthopedics"
    cardiology = "cardiology"
    gynecology = "gynecology"
    ent = "ent"


# code -> (display name, token prefix)
DEPARTMENTS: dict[Department, tuple[str, str]] = {
    Department.general_medicine: ("General Medicine", "GM"),
    Department.pediatrics: ("Pediatrics", "PD"),
    Department.orthopedics: ("Orthopedics", "OR"),
    Department.cardiology: ("Cardiology", "CD"),
    Department.gynecology: ("Gynecology", "GY"),
    Department.ent: ("ENT", "EN"),
}


class TokenStatus(str, Enum):
    waiting = "waiting"
    in_consultation = "in_consultation"
    prescribed = "prescribed"
    pharmacy = "pharmacy"
    completed = "completed"


# Registration -> Token -> Queue -> Consultation -> Prescription -> Pharmacy
TOKEN_FLOW = (
    TokenStatus.waiting,
    TokenStatus.in_consultation,
    TokenStatus.prescribed,
    TokenStatus.pharmacy,
    TokenStatus.completed,
)


class PatientRegistration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    patient_name: str = Field(min_length=2, max_length=100, examples=["Asha Verma"])
    age: int = Field(ge=0, le=120, examples=[34])
    # The phone number is the patient's permanent ID across visits, so it is required.
    # Exactly 10 digits (no +91, spaces or dashes) keeps one patient from getting two IDs.
    phone: str = Field(pattern=r"^\d{10}$", examples=["9876543210"])
    department: Department
    complaint: str | None = Field(default=None, max_length=300, examples=["Fever for 3 days"])


class TokenStatusUpdate(BaseModel):
    status: TokenStatus


class Token(BaseModel):
    token: str = Field(examples=["GM-007"])
    sequence: int
    patient_name: str
    age: int
    # No phone number here: these endpoints are open, and the phone is the patient's identity.
    department: Department
    department_name: str
    complaint: str | None
    status: TokenStatus
    registered_at: datetime
    updated_at: datetime
    # Only meaningful while status == waiting
    position: int | None = Field(default=None, description="1 = next to be called.")
    estimated_wait_minutes: int | None = None


class DepartmentQueue(BaseModel):
    code: Department
    name: str
    prefix: str
    now_serving: str | None
    waiting: int
