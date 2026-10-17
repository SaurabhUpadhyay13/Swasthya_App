import os
import tempfile

# Must happen before the app is imported: tests never touch the real data/ folder or load demo data.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="careflow-tests-")
os.environ["SEED_DEMO_DATA"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services.opd import OpdStore, get_opd_store
from app.services.work_orders import WorkOrderStore, get_work_order_store


@pytest.fixture
def supply():
    return WorkOrderStore()


@pytest.fixture
def opd(supply):
    return OpdStore(avg_consult_minutes=10, supply=supply)


@pytest.fixture
def wired(supply, opd):
    """The app wired to fresh, empty stores and a known config for every test."""
    app.dependency_overrides[get_work_order_store] = lambda: supply
    app.dependency_overrides[get_opd_store] = lambda: opd
    app.dependency_overrides[get_settings] = lambda: Settings(nvidia_api_key="test-key", _env_file=None)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def anon(wired):
    """A visitor who is not logged in."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(wired, opd):
    """Logged in as an administrator, who may use every shared endpoint (the queue, work orders, summaries).

    A request that passes its own Authorization header (a doctor, staff member or patient) overrides this one.
    """
    opd.admins.add("Test Admin", "TEST-ADMIN", "admin-password")
    token, _, _ = opd.admins.login("TEST-ADMIN", "admin-password")
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as test_client:
        yield test_client
