from fastapi import APIRouter, Depends, status

from app.auth import Principal, require_roles
from app.errors import ErrorResponse, api_error
from app.schemas.opd import (
    Department,
    DepartmentQueue,
    PatientRegistration,
    Token,
    TokenStatus,
    TokenStatusUpdate,
)
from app.services.opd import OpdStore, get_opd_store

router = APIRouter(prefix="/opd", tags=["OPD queue"])

_not_found = {404: {"model": ErrorResponse, "description": "Token not found"}}
_login_needed = {
    401: {"model": ErrorResponse, "description": "Not logged in or session expired"},
    403: {"model": ErrorResponse, "description": "This login's role cannot do this"},
}

# Who may use the queue: the OPD desk and the administrator; doctors may only move tokens of their own department.
desk = Depends(require_roles("staff", "admin"))
anyone_at_work = Depends(require_roles("doctor", "staff", "admin"))


@router.post("/tokens", response_model=Token, status_code=status.HTTP_201_CREATED, responses=_login_needed)
def register_patient(data: PatientRegistration, _=desk, store: OpdStore = Depends(get_opd_store)):
    """Register a patient and issue the next OPD token for the chosen department."""
    return store.register(data)


@router.get("/tokens", response_model=list[Token], responses=_login_needed)
def list_tokens(
    department: Department | None = None,
    status: TokenStatus | None = None,
    _=desk,
    store: OpdStore = Depends(get_opd_store),
):
    """Tokens in registration order, optionally filtered by department and/or status."""
    return store.list_tokens(department, status)


@router.get("/tokens/{token}", response_model=Token, responses={**_not_found, **_login_needed})
def get_token(token: str, _=desk, store: OpdStore = Depends(get_opd_store)):
    """A token with its live queue position and estimated wait."""
    return store.get(token)


@router.patch(
    "/tokens/{token}/status",
    response_model=Token,
    responses={
        **_not_found,
        **_login_needed,
        409: {"model": ErrorResponse, "description": "Invalid transition or doctor busy"},
    },
)
def update_token_status(
    token: str,
    update: TokenStatusUpdate,
    who: Principal = anyone_at_work,
    store: OpdStore = Depends(get_opd_store),
):
    """waiting → in_consultation → prescribed → pharmacy → completed."""
    if who.role == "doctor" and store.get(token).department != who.who.department:
        raise api_error(403, "wrong_department", f"Token {token.upper()} is not in your department.")
    return store.update_status(token, update.status)


@router.get("/departments", response_model=list[DepartmentQueue], responses=_login_needed)
def department_queues(_=anyone_at_work, store: OpdStore = Depends(get_opd_store)):
    """Per department: the token currently being served and how many are waiting."""
    return store.departments()
