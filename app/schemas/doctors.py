from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.opd import Department, Token, TokenStatus


class DoctorLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100, examples=["Dr. Asha Rao"])
    medical_id: str = Field(min_length=3, max_length=40, examples=["MH-2026-1001"])


class Doctor(BaseModel):
    id: int
    name: str
    medical_id: str
    department: Department
    department_name: str


class LoginResponse(BaseModel):
    token: str = Field(description="Send as 'Authorization: Bearer <token>'.")
    expires_at: datetime
    doctor: Doctor


class PrescriptionLine(BaseModel):
    """One medicine the doctor prescribes. It must exist in the OPD medicine list."""

    model_config = ConfigDict(str_strip_whitespace=True)

    medicine_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)
    instructions: str | None = Field(default=None, max_length=200, examples=["1 tablet twice a day for 5 days"])


class ConsultationSave(BaseModel):
    """The doctor's notes and prescription for the visit. Saving replaces what was saved before."""

    model_config = ConfigDict(str_strip_whitespace=True)

    remarks: str = Field(default="", max_length=4000)
    prescription: list[PrescriptionLine] = Field(default_factory=list, max_length=20)

    @field_validator("prescription")
    @classmethod
    def _each_medicine_once(cls, lines: list[PrescriptionLine]) -> list[PrescriptionLine]:
        ids = [line.medicine_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each medicine can be added only once.")
        return lines


class PrescriptionItem(BaseModel):
    medicine_id: int
    medicine_name: str
    quantity: int
    instructions: str | None
    prescribed_at: datetime
    # Filled in when the patient's token is completed at the pharmacy. Lower than quantity = short on stock.
    dispensed_quantity: int | None
    dispensed_at: datetime | None


class Visit(BaseModel):
    """One earlier visit of the same patient (matched by phone number)."""

    token: str
    department: Department
    department_name: str
    registered_at: datetime
    status: TokenStatus
    complaint: str | None
    doctor_name: str | None
    remarks: str | None
    prescription: list[PrescriptionItem]


class Consultation(BaseModel):
    token: Token
    patient_phone: str
    remarks: str
    prescription: list[PrescriptionItem]
    previous_visits: list[Visit]


class Dashboard(BaseModel):
    doctor: Doctor
    waiting: int = Field(description="Patients waiting right now in the doctor's department.")
    current: Token | None = Field(description="The patient currently in consultation, if any.")
    queue: list[Token] = Field(description="Waiting patients, next one first.")
