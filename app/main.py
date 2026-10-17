from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.errors import register_error_handlers
from app.routers import admin, doctors, opd, patients, staff, summarize, work_orders
from app.services.opd import get_opd_store
from app.services.seed import seed_demo_data
from app.services.work_orders import get_work_order_store

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    orders = get_work_order_store(settings)  # opens (or creates) data/supply_chain.db
    opd = get_opd_store(settings, orders)  # opens (or creates) data/opd.db
    if settings.seed_demo_data:
        seed_demo_data(orders, opd)
    yield


app = FastAPI(
    title="Swasthya AI API",
    description="Hospital OPD queue and medicine replenishment tracker.",
    version="0.1.0",
    lifespan=lifespan,
)
register_error_handlers(app)

app.include_router(work_orders.router)
app.include_router(opd.router)
app.include_router(doctors.router)
app.include_router(staff.router)
app.include_router(admin.router)
app.include_router(patients.router)
app.include_router(summarize.router)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}


# Mounted last so it never shadows the API routes or /docs.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
