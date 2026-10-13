from fastapi import APIRouter, Depends, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.errors import ErrorResponse, api_error
from app.schemas.doctors import (
    Consultation,
    ConsultationSave,
    Dashboard,
    Doctor,
    DoctorLogin,
    LoginResponse,
)
from app.schemas.medicines import Medicine
from app.schemas.opd import TokenStatus
from app.services.opd import OpdStore, get_opd_store
from app.services.work_orders import WorkOrderStore, get_work_order_store

router = APIRouter(prefix="/doctor", tags=["Doctor"])

# auto_error=False so a missing header gives our structured error instead of FastAPI's default.
_bearer = HTTPBearer(auto_error=False)

_unauthorised = {401: {"model": ErrorResponse, "description": "Not logged in or session expired"}}


def get_current_doctor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    store: OpdStore = Depends(get_opd_store),
) -> Doctor:
    if credentials is None:
        raise api_error(401, "not_authenticated", "Please log in.")
    doctor = store.doctors.from_session(credentials.credentials)
    if doctor is None:
        raise api_error(401, "session_expired", "Your session has ended. Please log in again.")
    return doctor


@router.post("/login", response_model=LoginResponse, responses={401: _unauthorised[401]})
def login(body: DoctorLogin, store: OpdStore = Depends(get_opd_store)):
    """Log in with your name and registered medical ID."""
    result = store.doctors.login(body.name, body.medical_id)
    if result is None:
        # Same message whichever part is wrong, so it does not reveal which names exist.
        raise api_error(401, "invalid_credentials", "Name or medical ID not recognised.")
    token, expires_at, doctor = result
    return LoginResponse(token=token, expires_at=expires_at, doctor=doctor)


@router.post("/logout", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    store: OpdStore = Depends(get_opd_store),
):
    if credentials:
        store.doctors.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/dashboard", response_model=Dashboard, responses=_unauthorised)
def dashboard(doctor: Doctor = Depends(get_current_doctor), store: OpdStore = Depends(get_opd_store)):
    """Live view of the doctor's own department: who is waiting and who is in consultation."""
    waiting = store.list_tokens(doctor.department, TokenStatus.waiting)
    current = store.list_tokens(doctor.department, TokenStatus.in_consultation)
    return Dashboard(doctor=doctor, waiting=len(waiting), current=current[0] if current else None, queue=waiting)


@router.get(
    "/consultations/{token}",
    response_model=Consultation,
    responses={**_unauthorised, 403: {"model": ErrorResponse, "description": "Patient is in another department"}},
)
def get_consultation(token: str, doctor: Doctor = Depends(get_current_doctor), store: OpdStore = Depends(get_opd_store)):
    """Saved remarks and prescription for this visit, plus the patient's earlier visits (matched by phone)."""
    return store.get_consultation(token, doctor)


@router.put(
    "/consultations/{token}",
    response_model=Consultation,
    responses={
        **_unauthorised,
        403: {"model": ErrorResponse, "description": "Patient is in another department"},
        409: {"model": ErrorResponse, "description": "Patient is not in consultation"},
        422: {"model": ErrorResponse, "description": "Invalid data or unknown medicine"},
    },
)
def save_consultation(
    token: str,
    body: ConsultationSave,
    doctor: Doctor = Depends(get_current_doctor),
    store: OpdStore = Depends(get_opd_store),
):
    """Save remarks and the prescription. Each save replaces the previous one for this visit."""
    return store.save_consultation(token, doctor, body)


@router.get("/medicines", response_model=list[Medicine], responses=_unauthorised)
def search_medicines(
    q: str = Query(min_length=1, max_length=60, description="Part of the medicine name"),
    _: Doctor = Depends(get_current_doctor),
    supply: WorkOrderStore = Depends(get_work_order_store),
):
    """Search the OPD medicine list and see how much is in stock right now."""
    return supply.search_medicines(q)
