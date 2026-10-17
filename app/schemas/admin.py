"""Requests and responses for the administrator: login, the hospital-wide dashboard, and adding people and stock."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.accounts import Staff
from app.schemas.doctors import Doctor
from app.schemas.medicines import Medicine
from app.schemas.opd import Department, DepartmentQueue


class AdminLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    admin_id: str = Field(min_length=3, max_length=40, examples=["ADMIN-001"])
    password: str = Field(min_length=1, max_length=72)


class Admin(BaseModel):
    id: int
    name: str
    admin_id: str


class AdminLoginResponse(BaseModel):
    token: str = Field(description="Send as 'Authorization: Bearer <token>'.")
    expires_at: datetime
    admin: Admin


class DoctorCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100, examples=["Dr. Asha Rao"])
    medical_id: str = Field(min_length=3, max_length=40, examples=["MH-2026-1001"])
    department: Department


class StaffCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=100, examples=["Meena Joshi"])
    staff_id: str = Field(min_length=3, max_length=40, examples=["OPD-001"])


class StockAdd(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    medicine: str = Field(min_length=2, max_length=100, examples=["Paracetamol 500mg"])
    quantity: int = Field(ge=1, le=1_000_000)


class Today(BaseModel):
    registered: int
    waiting: int
    in_consultation: int
    completed: int
    cancelled: int
    average_wait_minutes: float | None = Field(description="Registration to first call-in, for patients registered today.")


class Totals(BaseModel):
    patients: int
    visits: int
    doctors: int
    staff: int


class DayCount(BaseModel):
    date: str = Field(description="Local calendar day, YYYY-MM-DD")
    visits: int


class DoctorActivity(Doctor):
    online: bool = Field(description="Has a live login session right now.")
    seen_today: int
    seen_total: int
    prescribed_today: int = Field(description="Medicine lines prescribed today.")
    last_active_at: datetime | None
    waiting_in_department: int


class StaffMember(Staff):
    created_at: datetime


class DispensedItem(BaseModel):
    medicine: str
    quantity: int


class Pharmacy(BaseModel):
    medicines: int
    out_of_stock: int
    low_stock_level: int
    low_stock: list[Medicine] = Field(description="At or below the low-stock level, lowest first (at most 8).")
    dispensed_today_units: int
    dispensed_today: list[DispensedItem] = Field(description="Most dispensed medicines today (at most 5).")
    open_work_orders: int
    critical_open_work_orders: int
    work_orders_by_status: dict[str, int]


class ActivityEvent(BaseModel):
    at: datetime
    kind: str = Field(description="'opd' or 'stock'")
    text: str


class AdminDashboard(BaseModel):
    admin: Admin
    today: Today
    totals: Totals
    visits_last_7_days: list[DayCount]
    departments: list[DepartmentQueue]
    doctors: list[DoctorActivity]
    staff: list[StaffMember]
    pharmacy: Pharmacy
    recent_activity: list[ActivityEvent]
