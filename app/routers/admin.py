from fastapi import APIRouter, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import require_roles
from app.errors import ErrorResponse, api_error
from app.routers.staff import LOW_STOCK_LEVEL
from app.schemas.accounts import Staff
from app.schemas.admin import (
    ActivityEvent,
    Admin,
    AdminDashboard,
    AdminLogin,
    AdminLoginResponse,
    DispensedItem,
    DoctorCreate,
    Pharmacy,
    StaffCreate,
    StockAdd,
)
from app.schemas.doctors import Doctor
from app.schemas.medicines import Medicine
from app.services.opd import OpdStore, get_opd_store
from app.services.work_orders import WorkOrderStore, get_work_order_store

router = APIRouter(prefix="/admin", tags=["Admin"])

_bearer = HTTPBearer(auto_error=False)
_protected = {
    401: {"model": ErrorResponse, "description": "Not logged in or session expired"},
    403: {"model": ErrorResponse, "description": "Logged in, but not as an administrator"},
}


def get_current_admin(principal=Depends(require_roles("admin"))) -> Admin:
    return principal.who


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    responses={401: _protected[401], 429: {"model": ErrorResponse, "description": "Too many wrong passwords"}},
)
def login(body: AdminLogin, store: OpdStore = Depends(get_opd_store)):
    """Log in with your admin ID and password."""
    result = store.admins.login(body.admin_id, body.password)
    if result is None:
        raise api_error(401, "invalid_credentials", "Admin ID or password is not correct.")
    token, expires_at, admin = result
    return AdminLoginResponse(token=token, expires_at=expires_at, admin=admin)


@router.post("/logout", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    store: OpdStore = Depends(get_opd_store),
):
    if credentials:
        store.admins.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/dashboard", response_model=AdminDashboard, responses=_protected)
def dashboard(
    admin: Admin = Depends(get_current_admin),
    store: OpdStore = Depends(get_opd_store),
    supply: WorkOrderStore = Depends(get_work_order_store),
):
    """Everything in one view: today's OPD numbers, department queues, every doctor's activity, pharmacy and a live feed."""
    overview = store.admin_overview()
    stock = supply.stock_summary(LOW_STOCK_LEVEL)
    dispensed = [DispensedItem(**row) for row in overview.pop("dispensed_today")]
    opd_feed = overview.pop("opd_feed")
    stock_feed = [
        {
            "at": e["occurred_at"],
            "kind": "stock",
            "text": f"Work order #{e['work_order_id']} for {e['medicine_name']} "
            + ("was raised" if e["from_status"] is None else f"moved to {e['to_status']}"),
        }
        for e in stock["events"]
    ]
    feed = sorted(opd_feed + stock_feed, key=lambda e: e["at"], reverse=True)[:12]
    pharmacy = Pharmacy(
        medicines=stock["medicines"],
        out_of_stock=stock["out_of_stock"],
        low_stock_level=LOW_STOCK_LEVEL,
        low_stock=stock["low_stock"],
        dispensed_today_units=sum(d.quantity for d in dispensed),
        dispensed_today=dispensed[:5],
        open_work_orders=stock["by_status"]["requested"] + stock["by_status"]["ordered"] + stock["by_status"]["received"],
        critical_open_work_orders=stock["critical_open"],
        work_orders_by_status=stock["by_status"],
    )
    return AdminDashboard(
        admin=admin, pharmacy=pharmacy, recent_activity=[ActivityEvent(**e) for e in feed], **overview
    )


def _conflict(error: ValueError):
    return api_error(409, "already_registered", str(error))


@router.post("/doctors", response_model=Doctor, status_code=status.HTTP_201_CREATED, responses=_protected)
def add_doctor(body: DoctorCreate, _: Admin = Depends(get_current_admin), store: OpdStore = Depends(get_opd_store)):
    """Register a doctor. They log in on the Doctor desk with this name and medical ID."""
    try:
        return store.doctors.add(body.name, body.medical_id, body.department)
    except ValueError as error:
        raise _conflict(error) from None


@router.post("/staff", response_model=Staff, status_code=status.HTTP_201_CREATED, responses=_protected)
def add_staff(body: StaffCreate, _: Admin = Depends(get_current_admin), store: OpdStore = Depends(get_opd_store)):
    """Register an OPD staff member. They log in on the OPD desk with this name and staff ID."""
    try:
        return store.staff.add(body.name, body.staff_id)
    except ValueError as error:
        raise _conflict(error) from None


@router.post("/stock", response_model=Medicine, status_code=status.HTTP_201_CREATED, responses=_protected)
def add_stock(body: StockAdd, _: Admin = Depends(get_current_admin), supply: WorkOrderStore = Depends(get_work_order_store)):
    """Add medicine to the OPD stock (an opening balance or a manual top-up). Creates the medicine if it is new."""
    return supply.add_stock(body.medicine, body.quantity)
