"""Requests and responses for OPD staff login and patient login."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.doctors import Visit
from app.schemas.medicines import Medicine
from app.schemas.opd import Department, DepartmentQueue, Token

PHONE = r"^\d{10}$"


# ---- OPD staff -----------------------------------------------------------------------

class StaffLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100, examples=["Meena Joshi"])
    staff_id: str = Field(min_length=3, max_length=40, examples=["OPD-001"])


class Staff(BaseModel):
    id: int
    name: str
    staff_id: str


class StaffLoginResponse(BaseModel):
    token: str = Field(description="Send as 'Authorization: Bearer <token>'.")
    expires_at: datetime
    staff: Staff


class PatientCodeRequest(BaseModel):
    phone: str = Field(pattern=PHONE, examples=["9876543210"])


class AccessCode(BaseModel):
    """A one-time code the OPD desk gives to the patient so they can set their own password."""

    phone: str
    patient_name: str
    code: str
    expires_at: datetime


class StaffDashboard(BaseModel):
    staff: Staff
    waiting: int
    in_consultation: int
    registered_today: int
    completed_today: int
    departments: list[DepartmentQueue]
    low_stock: list[Medicine] = Field(description="Medicines at or below the low-stock level, lowest first.")
    low_stock_level: int
    open_work_orders: int
    critical_open_work_orders: int = Field(description="Critical orders that have not been received yet.")


# ---- Patients -------------------------------------------------------------------------

class PatientActivate(BaseModel):
    """First login: the code from the OPD desk plus a password the patient chooses."""

    phone: str = Field(pattern=PHONE)
    code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=8, max_length=72)


class PatientSignupStart(BaseModel):
    """A new patient's details. The phone number must not be in the hospital's records yet."""

    model_config = ConfigDict(str_strip_whitespace=True)

    phone: str = Field(pattern=PHONE)
    name: str = Field(min_length=2, max_length=100, examples=["Asha Verma"])
    age: int = Field(ge=0, le=120)


class SignupCode(BaseModel):
    """Shown on the patient's own screen. It expires quickly and works once."""

    code: str
    expires_in_seconds: int


class PatientSignup(BaseModel):
    phone: str = Field(pattern=PHONE)
    code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=8, max_length=72)


class PatientTokenRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    department: Department
    complaint: str | None = Field(default=None, max_length=300, examples=["Fever for 3 days"])


class PatientLogin(BaseModel):
    phone: str = Field(pattern=PHONE)
    password: str = Field(min_length=1, max_length=72)


class PatientProfile(BaseModel):
    phone: str
    name: str
    age: int


class PatientLoginResponse(BaseModel):
    token: str = Field(description="Send as 'Authorization: Bearer <token>'.")
    expires_at: datetime
    patient: PatientProfile


class PatientDashboard(BaseModel):
    patient: PatientProfile
    current: Token | None = Field(description="The patient's token while the visit is still open.")
    departments: list[DepartmentQueue] = Field(description="Live queue of every department, to choose from.")
    minutes_per_patient: int = Field(description="Used for the estimated wait: patients waiting x this.")
    visits: list[Visit] = Field(description="All other visits, newest first, with doctor remarks and medicines.")
    total_visits: int
