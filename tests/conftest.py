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
def client(supply, opd):
    """A client wired to fresh, empty stores and a known config for every test."""
    app.dependency_overrides[get_work_order_store] = lambda: supply
    app.dependency_overrides[get_opd_store] = lambda: opd
    app.dependency_overrides[get_settings] = lambda: Settings(groq_api_key="test-key", _env_file=None)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
