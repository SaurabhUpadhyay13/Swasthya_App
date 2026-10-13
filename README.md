# CareFlow

A FastAPI service plus a web app for a hospital OPD (outpatient department) and its medicine supply.

**What it does**

1. **Medicine supply chain.** A stock-out becomes a replenishment work order: *Requested → Ordered → Received → Completed*. Receiving an order adds to the OPD stock.
2. **OPD queue.** A patient registers (phone number required), gets a department token, and moves through *Waiting → In consultation → Prescribed → Pharmacy → Completed*.
3. **Doctor desk.** Doctors log in, see how many patients are waiting in their department, write remarks, and prescribe medicines while seeing live stock.
4. **OPD staff desk.** Staff log in to a hospital-wide dashboard and hand patients a one-time code to open their account.
5. **Patient portal.** Patients log in with phone number and password and see their live token, every earlier visit, the doctor's remarks and the medicines they received.
6. **AI summary.** `POST /summarize` summarises a work order using Groq (free tier).

Everything is stored in SQLite files, so data survives restarts.

---

## Project structure

```
careflow/
├── app/
│   ├── main.py             # App creation, router wiring, serves the frontend
│   ├── config.py           # Settings from .env (API key never hardcoded)
│   ├── errors.py           # One structured error shape for every failure
│   ├── workflow.py         # "One step forward only" rule for both workflows
│   ├── db.py               # SQLite helpers, exact UTC timestamps
│   ├── cli.py              # Admin commands: add doctors, staff and stock
│   ├── schemas/            # Pydantic request/response models
│   │   ├── work_orders.py  opd.py  summarize.py
│   │   ├── doctors.py  medicines.py
│   │   └── accounts.py     # staff and patient login, dashboards
│   ├── routers/            # HTTP layer, one file per feature
│   │   ├── work_orders.py  opd.py  summarize.py
│   │   ├── doctors.py      # /doctor/...
│   │   ├── staff.py        # /staff/...
│   │   └── patients.py     # /patient/...
│   └── services/           # Business logic and storage
│       ├── work_orders.py  # supply_chain.db: orders, events, medicine stock
│       ├── opd.py          # opd.db: patients, tokens, events, consultations, prescriptions
│       ├── doctors.py      # doctors and their sessions
│       ├── accounts.py     # staff, patient passwords, access codes, sessions
│       ├── llm.py          # Groq client
│       └── seed.py         # Optional demo data
├── frontend/               # Plain HTML/CSS/JS, no build step
│   ├── index.html
│   ├── css/ (styles, doctor, accounts)
│   └── js/ (main, api, ui, icons, views/*)
├── tests/                  # pytest, 74 tests, LLM calls mocked
├── data/                   # Created on first run: opd.db, supply_chain.db (git-ignored)
├── .env.example            # Copy to .env
├── requirements.txt
└── README.md
```

---

## Run it, step by step

**You need:** Python 3.11 or newer.

1. **Open the project folder**
   ```bash
   cd careflow
   ```
2. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Create your `.env` file**
   ```bash
   cp .env.example .env               # Windows: copy .env.example .env
   ```
5. **Add your Groq key** (only needed for the summarize feature). Create a free key at <https://console.groq.com/keys> and put it in `.env` as `GROQ_API_KEY=gsk_...`. `.env` is git-ignored: never commit it.
6. **Start the server**
   ```bash
   uvicorn app.main:app --reload
   ```
7. **Open the app:** <http://localhost:8000> (API docs: <http://localhost:8000/docs>)
8. **Run the tests** (no internet or Groq key needed)
   ```bash
   pytest
   ```

### Set up people and stock (run once, with the server stopped or running)

```bash
python -m app.cli add-doctor "Dr. Asha Rao" MH-2026-1001 general_medicine
python -m app.cli add-staff  "Meena Joshi" OPD-001
python -m app.cli add-stock  "Paracetamol 500mg" 500
```

Department codes: `general_medicine`, `pediatrics`, `orthopedics`, `cardiology`, `gynecology`, `ent`.

Or set `SEED_DEMO_DATA=true` in `.env` for a first start with sample data and these demo logins:

| Role | Login |
|---|---|
| Doctor | Dr. Asha Rao / `DEMO-1001` |
| OPD staff | Meena Joshi / `DEMO-STAFF` |
| Patient | phone `9876500001` / password `careflow-demo` |

---

## How each role uses the app

### Doctor desk
1. Log in with your **name and medical ID**.
2. The dashboard shows a live count of patients waiting in **your department** (refreshes every 5 seconds).
3. **Call** the next patient. Write remarks. The patient's earlier visits (matched by phone number) appear beside the notes.
4. Search the OPD medicine list while prescribing. Each result shows live stock, and you are warned if the quantity exceeds what is in stock.
5. **Save notes** any time, or **Finish consultation** to send the patient on to the pharmacy.

### OPD staff desk
1. Log in with your **name and staff ID**.
2. See waiting and in-consultation patients, today's registrations and completions, every department's queue, medicines at or below 20 units, and open medicine orders.
3. **Patient access code:** enter a patient's phone number to get a 6-digit one-time code. Tell it to the patient in person.

### Patient portal
1. **First time:** the OPD desk gives you a code. Open **Patient portal → First time here?**, enter your phone number, the code, and choose a password (8 or more characters).
2. **Afterwards:** log in with phone number and password.
3. You see your live token with place in line, then all earlier visits with the doctor's remarks and the medicines you were given.
4. **Forgot your password?** Ask the OPD desk for a new code. The same flow resets it.

---

## Data storage

Two SQLite files in `data/`, created automatically:

| File | Contents |
|---|---|
| `supply_chain.db` | `work_orders`, `work_order_events` (every status change, timestamped), `medicines` (live stock) |
| `opd.db` | `patients` (phone number is the primary key), `opd_tokens` (one row per visit), `opd_events` (every step, timestamped, no personal data), `consultations`, `prescription_items` (prescribed and dispensed quantities), `doctors`, `staff`, `patient_accounts` (password hashes), `access_codes`, `account_sessions`, `doctor_sessions` |

All times are UTC ISO-8601 with microseconds. For analysis use the `*_events` tables. **`opd.db` holds names, phone numbers and doctor remarks: do not share it.** Share exports of `opd_events` instead.

Stock rules: a work order marked *Received* adds its quantity to stock. Completing a token at the pharmacy removes the prescribed medicines from stock. If stock is short the patient gets what is available and the shortfall stays on record (`dispensed_quantity` below `quantity`).

---

## Security notes

- **Patients:** phone number plus password. Passwords are stored as salted scrypt hashes. A patient can only create or reset a password with a one-time code from the OPD desk (valid 24 hours, works once, locks after 5 wrong tries), so knowing a phone number is not enough to read someone's record.
- **Doctors and staff:** name plus ID, no password. Anyone who knows a doctor's name and medical ID can log in as them. Add a PIN or password before real use.
- Sessions are random tokens; only their hash is stored. Staff and doctor sessions last 12 hours, patient sessions 24.
- **Not protected yet:** the Overview, OPD queue, Track a token and Medicine stock pages, and the endpoints behind them, are still open to anyone who can reach the server. Do not expose the app to the internet as it is.
- There is no limit on wrong *password* attempts yet.
- One phone number is one patient: family members who share a phone share one record.

---

## API reference

Errors always look like:

```json
{ "error": { "code": "invalid_credentials", "message": "Name or staff ID not recognised." } }
```

Validation errors (`422`) add a `details` list of `{field, message}`. Logged-in endpoints expect `Authorization: Bearer <token>` from the matching login.

### Medicine work orders
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/work-orders` | Create (starts as `requested`) |
| `GET` | `/work-orders?status=` | List, newest first |
| `GET` | `/work-orders/{id}` | Get one |
| `PATCH` | `/work-orders/{id}/status` | Move one step forward (`409 invalid_status_transition`) |
| `POST` | `/summarize` | AI summary of a work order (`503 llm_not_configured` without a key) |

### OPD queue
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/opd/tokens` | Register a patient (`phone`: exactly 10 digits), get a token such as `GM-004` |
| `GET` | `/opd/tokens?department=&status=` | List tokens |
| `GET` | `/opd/tokens/{token}` | One token with `position` and `estimated_wait_minutes` |
| `PATCH` | `/opd/tokens/{token}/status` | Advance one step (`409 doctor_busy` if the doctor has someone in) |
| `GET` | `/opd/departments` | Per department: now serving and number waiting |

### Doctor
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/doctor/login` | `{name, medical_id}` returns a token |
| `POST` | `/doctor/logout` | End the session |
| `GET` | `/doctor/dashboard` | Waiting count, current patient, queue |
| `GET` | `/doctor/consultations/{token}` | Remarks, prescription and earlier visits (`403 wrong_department`) |
| `PUT` | `/doctor/consultations/{token}` | Save remarks and prescription (`409 not_in_consultation`) |
| `GET` | `/doctor/medicines?q=` | Search medicines with live stock |

### OPD staff
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/staff/login` | `{name, staff_id}` returns a token |
| `POST` | `/staff/logout` | End the session |
| `GET` | `/staff/dashboard` | Queues, today's counts, low stock, open orders |
| `POST` | `/staff/patient-codes` | `{phone}` returns a one-time code (`404 patient_not_found`) |

### Patient
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/patient/activate` | `{phone, code, password}` sets the password and logs in (`401 invalid_code`) |
| `POST` | `/patient/login` | `{phone, password}` returns a token (`401 invalid_credentials`) |
| `POST` | `/patient/logout` | End the session |
| `GET` | `/patient/dashboard` | Live token and all visits with remarks and medicines |

---

## Design decisions (YAGNI)

Built because the brief needs it: the workflows, validation, structured errors, SQLite storage, three role logins and dashboards.
Left out until there is a real need:

- **Passwords for doctors and staff**, SMS or email codes, rate limiting, roles and permissions beyond "doctor / staff / patient".
- **Protecting the older staff pages.** Next step: require the staff login for them.
- **Migrations tool.** New tables are created automatically on start (`CREATE TABLE IF NOT EXISTS`); existing tables are never altered.
- **ORM, pagination, frontend framework, build step.** Plain `sqlite3` and ES modules are enough at this size.
- **Daily token reset, no-shows, cancelling tokens, editing a patient's phone number.**

## Roadmap

1. Require staff login on the queue and stock pages, and add a PIN for doctors.
2. Reset token numbers each day; handle no-shows.
3. Reporting from the `*_events` tables: waiting time per department, stock-out frequency, time to replenish.
4. Send access codes by SMS instead of reading them out.
5. Integration with existing hospital systems (HL7/FHIR or the hospital's HIS API).
6. Walk registration, pharmacy and doctors through the flows and adjust wording and departments.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GROQ_API_KEY` | none | Groq key for `/summarize` |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Chat model available to your Groq account |
| `AVG_CONSULT_MINUTES` | `10` | Used for the estimated wait |
| `SEED_DEMO_DATA` | `false` | Load sample data on the **first** start only (empty databases) |
| `DATA_DIR` | `data` | Folder for the two database files |
