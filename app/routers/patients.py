from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.errors import ErrorResponse, api_error
from app.schemas.accounts import (
    PatientActivate,
    PatientDashboard,
    PatientLogin,
    PatientLoginResponse,
)
from app.services.opd import OpdStore, get_opd_store

router = APIRouter(prefix="/patient", tags=["Patient"])

_bearer = HTTPBearer(auto_error=False)
_unauthorised = {401: {"model": ErrorResponse, "description": "Not logged in or session expired"}}


def get_current_phone(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    store: OpdStore = Depends(get_opd_store),
) -> str:
    if credentials is None:
        raise api_error(401, "not_authenticated", "Please log in.")
    phone = store.patient_accounts.phone_from_session(credentials.credentials)
    if phone is None:
        raise api_error(401, "session_expired", "Your session has ended. Please log in again.")
    return phone


def _logged_in(store: OpdStore, phone: str) -> PatientLoginResponse:
    token, expires_at = store.patient_accounts.start_session(phone)
    return PatientLoginResponse(token=token, expires_at=expires_at, patient=store.patient_dashboard(phone).patient)


@router.post("/activate", response_model=PatientLoginResponse, responses={401: _unauthorised[401]})
def activate(body: PatientActivate, store: OpdStore = Depends(get_opd_store)):
    """First login (or password reset): the one-time code from the OPD desk plus a password you choose."""
    if not store.patient_accounts.activate(body.phone, body.code, body.password):
        raise api_error(401, "invalid_code", "That code is not valid or has expired. Ask the OPD desk for a new one.")
    return _logged_in(store, body.phone)


@router.post("/login", response_model=PatientLoginResponse, responses={401: _unauthorised[401]})
def login(body: PatientLogin, store: OpdStore = Depends(get_opd_store)):
    """Log in with your phone number and password."""
    if not store.patient_accounts.verify(body.phone, body.password):
        # Same message whichever part is wrong, so it does not reveal which phone numbers are registered.
        raise api_error(401, "invalid_credentials", "Phone number or password is not correct.")
    return _logged_in(store, body.phone)


@router.post("/logout", status_code=204)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    store: OpdStore = Depends(get_opd_store),
):
    if credentials:
        store.patient_accounts.logout(credentials.credentials)
    return Response(status_code=204)


@router.get("/dashboard", response_model=PatientDashboard, responses=_unauthorised)
def dashboard(phone: str = Depends(get_current_phone), store: OpdStore = Depends(get_opd_store)):
    """Your live token and all your earlier visits: doctor remarks and medicines given."""
    return store.patient_dashboard(phone)
