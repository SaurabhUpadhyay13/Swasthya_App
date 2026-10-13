from fastapi import APIRouter, Depends, status

from app.errors import ErrorResponse
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


@router.post("/tokens", response_model=Token, status_code=status.HTTP_201_CREATED)
def register_patient(data: PatientRegistration, store: OpdStore = Depends(get_opd_store)):
    """Register a patient and issue the next OPD token for the chosen department."""
    return store.register(data)


@router.get("/tokens", response_model=list[Token])
def list_tokens(
    department: Department | None = None,
    status: TokenStatus | None = None,
    store: OpdStore = Depends(get_opd_store),
):
    """Tokens in registration order, optionally filtered by department and/or status."""
    return store.list_tokens(department, status)


@router.get("/tokens/{token}", response_model=Token, responses=_not_found)
def get_token(token: str, store: OpdStore = Depends(get_opd_store)):
    """A token with its live queue position and estimated wait."""
    return store.get(token)


@router.patch(
    "/tokens/{token}/status",
    response_model=Token,
    responses={**_not_found, 409: {"model": ErrorResponse, "description": "Invalid transition or doctor busy"}},
)
def update_token_status(token: str, update: TokenStatusUpdate, store: OpdStore = Depends(get_opd_store)):
    """waiting → in_consultation → prescribed → pharmacy → completed."""
    return store.update_status(token, update.status)


@router.get("/departments", response_model=list[DepartmentQueue])
def department_queues(store: OpdStore = Depends(get_opd_store)):
    """Per department: the token currently being served and how many are waiting."""
    return store.departments()
