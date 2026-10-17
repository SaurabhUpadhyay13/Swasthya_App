from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import start_of_day_utc
from app.errors import ErrorResponse, api_error
from app.schemas.accounts import (
    AccessCode,
    PatientCodeRequest,
    Staff,
    StaffDashboard,
    StaffLogin,
    StaffLoginResponse,
)
from app.schemas.work_orders import Priority, WorkOrderStatus
from app.services.opd import OpdStore, get_opd_store
from app.services.work_orders import WorkOrderStore, get_work_order_store

router = APIRouter(prefix="/staff", tags=["OPD staff"])

LOW_STOCK_LEVEL = 20  # at or below this many units, a medicine is shown as low

_bearer = HTTPBearer(auto_error=False)
_unauthorised = {401: {"model": ErrorResponse, "description": "Not logged in or session expired"}}


def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    store: OpdStore = Depends(get_opd_store),
) -> Staff:
    if credentials is None:
        raise api_error(401, "not_authenticated", "Please log in.")
    staff = store.staff.from_session(credentials.credentials)
    if staff is None:
        raise api_error(401, "session_expired", "Your session has ended. Please log in again.")
    return staff


@router.post("/login", response_model=StaffLoginResponse, responses={401: _unauthorised[401]})
def login(body: StaffLogin, store: OpdStore = Depends(get_opd_store)):
    """Log in with your name and registered staff ID."""
    result = store.staff.login(body.name, body.staff_id)
    if result is None:
        raise api_error(401, "invalid_credentials", "Name or staff ID not recognised.")
    token, expires_at, staff = result
    return StaffLoginResponse(token=token, expires_at=expires_at, staff=staff)


@router.post("/logout", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    store: OpdStore = Depends(get_opd_store),
):
    if credentials:
        store.staff.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/dashboard", response_model=StaffDashboard, responses=_unauthorised)
def dashboard(
    staff: Staff = Depends(get_current_staff),
    store: OpdStore = Depends(get_opd_store),
    supply: WorkOrderStore = Depends(get_work_order_store),
):
    """Hospital-wide live view: queues, today's numbers, low stock and open medicine orders."""
    orders = [o for o in supply.list_orders() if o.status != WorkOrderStatus.completed]
    critical = [o for o in orders if o.priority == Priority.critical and o.status != WorkOrderStatus.received]
    return StaffDashboard(
        staff=staff,
        **store.day_stats(start_of_day_utc()),
        departments=store.departments(),
        low_stock=supply.low_stock(LOW_STOCK_LEVEL),
        low_stock_level=LOW_STOCK_LEVEL,
        open_work_orders=len(orders),
        critical_open_work_orders=len(critical),
    )


@router.post(
    "/patient-codes",
    response_model=AccessCode,
    responses={**_unauthorised, 404: {"model": ErrorResponse, "description": "No patient with this phone number"}},
)
def issue_patient_code(
    body: PatientCodeRequest,
    _: Staff = Depends(get_current_staff),
    store: OpdStore = Depends(get_opd_store),
):
    """Give a patient a one-time code to set up (or reset) their login. Read it out or print it for them."""
    result = store.patient_accounts.issue_code(body.phone)
    if result is None:
        raise api_error(404, "patient_not_found", "No patient is registered with this phone number yet.")
    code, name, expires_at = result
    return AccessCode(phone=body.phone, patient_name=name, code=code, expires_at=expires_at)
