"""One place to say "only these roles may call this endpoint".

    Depends(require_roles("staff", "admin"))

Doctors, OPD staff and administrators each have their own login. A valid login of the wrong role gets
403 (you are who you say, but not allowed); a missing or expired one gets 401 (please log in).
"""

from typing import NamedTuple

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.errors import api_error
from app.services.opd import OpdStore, get_opd_store

_bearer = HTTPBearer(auto_error=False)


class Principal(NamedTuple):
    role: str  # "doctor", "staff" or "admin"
    who: object  # the Doctor, Staff or Admin record


def require_roles(*allowed: str):
    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        store: OpdStore = Depends(get_opd_store),
    ) -> Principal:
        if credentials is None:
            raise api_error(401, "not_authenticated", "Please log in.")
        token = credentials.credentials
        lookups = {
            "doctor": store.doctors.from_session,
            "staff": store.staff.from_session,
            "admin": store.admins.from_session,
            "patient": store.patient_accounts.phone_from_session,
        }
        for role in allowed:
            who = lookups[role](token)
            if who is not None:
                return Principal(role, who)
        if any(fn(token) is not None for role, fn in lookups.items() if role not in allowed):
            raise api_error(403, "forbidden", "Your login does not have access to this.")
        raise api_error(401, "session_expired", "Your session has ended. Please log in again.")

    return dependency
