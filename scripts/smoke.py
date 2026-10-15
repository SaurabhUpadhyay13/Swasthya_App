"""End-to-end smoke test against a RUNNING server. Uses the real HTTP API and the demo data. Runs in CI.

    SEED_DEMO_DATA=true uvicorn app.main:app &
    python scripts/smoke.py http://127.0.0.1:8000

It walks the journeys that matter: every page file is served, the three roles can log in, a walk-in is
registered, a new patient signs up and registers themself, and the "one open token per patient" rule holds
between the desk and the patient. Exit code 1 and a list of failures if anything is off.
"""

import random
import re
import sys

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'}  {name}{'' if ok else f'  -> {detail}'}")
    if not ok:
        failures.append(name)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def error_code(response: httpx.Response) -> str | None:
    try:
        return response.json()["error"]["code"]
    except Exception:
        return None


client = httpx.Client(base_url=BASE, timeout=15)

# ---- 1. The app and every page file it serves -------------------------------------------
check("GET /health", client.get("/health").status_code == 200)
home = client.get("/")
check("GET / serves the app", home.status_code == 200 and "CareFlow" in home.text)
check("GET /docs", client.get("/docs").status_code == 200)
paths = client.get("/openapi.json").json().get("paths", {})
for needed in ("/staff/login", "/doctor/login", "/patient/signup", "/patient/tokens", "/opd/tokens", "/work-orders"):
    check(f"API has {needed}", needed in paths)

assets = set(re.findall(r'(?:href|src)="(/(?:css|js)/[^"]+)"', home.text))
for js in ("/js/main.js", "/js/api.js", "/js/ui.js", "/js/views/staff.js", "/js/views/patient.js", "/js/views/doctor.js"):
    assets.add(js)
for asset in sorted(assets):
    check(f"serves {asset}", client.get(asset).status_code == 200)

# ---- 2. The three logins (demo data) ----------------------------------------------------
staff = client.post("/staff/login", json={"name": "Meena Joshi", "staff_id": "DEMO-STAFF"})
check("staff login", staff.status_code == 200, staff.text)
doctor = client.post("/doctor/login", json={"name": "Dr. Asha Rao", "medical_id": "DEMO-1001"})
check("doctor login", doctor.status_code == 200, doctor.text)
patient = client.post("/patient/login", json={"phone": "9876500001", "password": "careflow-demo"})
check("patient login", patient.status_code == 200, patient.text)
check("wrong staff ID is refused", client.post("/staff/login", json={"name": "Meena Joshi", "staff_id": "nope"}).status_code == 401)
if failures:
    sys.exit("Cannot continue without working logins.")

staff_h, doctor_h, patient_h = (auth(r.json()["token"]) for r in (staff, doctor, patient))

# ---- 3. Dashboards ----------------------------------------------------------------------
board = client.get("/staff/dashboard", headers=staff_h)
check("staff dashboard", board.status_code == 200 and len(board.json()["departments"]) >= 20, board.text)
check("doctor dashboard", client.get("/doctor/dashboard", headers=doctor_h).status_code == 200)
mine = client.get("/patient/dashboard", headers=patient_h)
check("patient dashboard shows live departments", mine.status_code == 200 and len(mine.json()["departments"]) >= 20, mine.text)
check("a staff token does not open the patient dashboard", client.get("/patient/dashboard", headers=staff_h).status_code == 401)
check("no token, no staff dashboard", client.get("/staff/dashboard").status_code == 401)

# ---- 4. Walk-in registration and the one-open-token rule ---------------------------------
suffix = random.randint(10**7, 10**8 - 1)
walk_phone, new_phone = f"90{suffix}", f"91{suffix}"
walk_in = {"patient_name": "Smoke Walkin", "age": 40, "phone": walk_phone, "department": "ent"}
first = client.post("/opd/tokens", json=walk_in)
check("walk-in registration", first.status_code == 201, first.text)
again = client.post("/opd/tokens", json={**walk_in, "department": "cardiology"})
check("same patient, second department is refused", again.status_code == 409 and error_code(again) == "already_in_queue", again.text)
if first.status_code == 201:
    cancel = client.patch(f"/opd/tokens/{first.json()['token']}/status", json={"status": "cancelled"})
    check("waiting token can be cancelled", cancel.status_code == 200, cancel.text)
    check("after cancelling, the patient can register again", client.post("/opd/tokens", json=walk_in).status_code == 201)

# ---- 5. A new patient signs up and registers themself ------------------------------------
start = client.post("/patient/signup/start", json={"phone": new_phone, "name": "Smoke Newpatient", "age": 31})
check("signup code issued", start.status_code == 200 and start.json().get("expires_in_seconds") == 60, start.text)
signup = client.post("/patient/signup", json={"phone": new_phone, "code": start.json().get("code", "000000"), "password": "smoke-test-pass"})
check("signup creates the account", signup.status_code == 200, signup.text)
if signup.status_code == 200:
    me = auth(signup.json()["token"])
    own = client.post("/patient/tokens", headers=me, json={"department": "pediatrics", "complaint": "smoke test"})
    check("patient registers themself", own.status_code == 201, own.text)
    by_desk = client.post("/opd/tokens", json={"patient_name": "Smoke Newpatient", "age": 31, "phone": new_phone, "department": "ent"})
    check("desk cannot also register that patient", by_desk.status_code == 409 and error_code(by_desk) == "already_in_queue", by_desk.text)
    check("patient sees their live token", (client.get("/patient/dashboard", headers=me).json().get("current") or {}).get("status") == "waiting")
    check("patient cancels their own token", client.post("/patient/tokens/cancel", headers=me).status_code == 200)
    check("existing phone cannot sign up again", client.post("/patient/signup/start", json={"phone": new_phone, "name": "X Y", "age": 1}).status_code == 409)

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for name in failures:
        print(f"  - {name}")
    sys.exit(1)
print("All smoke checks passed.")
