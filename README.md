# Swasthya AI

A FastAPI service plus a web app for a hospital OPD (outpatient department) and its medicine supply.

**What it does**

The app opens on a **login screen**. Nobody sees any data until they sign in, and each role then sees only its own pages: **Administrator**, **Doctor**, **OPD staff** or **Patient**.

0. **Administrator dashboard.** One screen for the whole hospital: today's OPD numbers, the live queue of every department (4 at a time, with a search box), every doctor's activity (online, patients seen, medicines prescribed, last active), pharmacy status (low and out-of-stock medicines, what was dispensed today, open and critical orders), a 7-day visit chart and a live activity feed. The administrator also adds doctors, OPD staff and stock from the browser, and manages the medicine work orders.
1. **Medicine supply chain.** A stock-out becomes a replenishment work order: *Requested → Ordered → Received → Completed*. Receiving an order adds to the OPD stock.
2. **OPD queue.** A patient gets a department token and moves through *Waiting → In consultation → Prescribed → Pharmacy → Completed*. A waiting token can be cancelled. **A patient can have only one open token at a time**, whoever registers them.
3. **Doctor desk.** Doctors log in, see how many patients are waiting in their department, write remarks, and prescribe medicines while seeing live stock.
4. **OPD staff desk.** Staff log in to one screen with the hospital-wide dashboard, **walk-in registration** (for patients who come to the desk or don't know which department to choose) and the live queue of every department.
5. **Patient portal.** A new patient creates their own account, sees the live queue of every department, registers themself in one, and later sees every visit, the doctor's remarks and the medicines they received.
6. **AI summary.** `POST /summarize` summarises a work order using an NVIDIA-hosted model (free tier).

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
│   ├── auth.py             # require_roles(...): which login may call which endpoint
│   ├── cli.py              # Server commands: add administrators, doctors, staff and stock
│   ├── schemas/            # Pydantic request/response models
│   │   ├── work_orders.py  opd.py  summarize.py
│   │   ├── doctors.py  medicines.py
│   │   ├── admin.py        # administrator login, dashboard, add people and stock
│   │   └── accounts.py     # staff and patient login, dashboards
│   ├── routers/            # HTTP layer, one file per feature
│   │   ├── work_orders.py  opd.py  summarize.py
│   │   ├── doctors.py      # /doctor/...
│   │   ├── admin.py        # /admin/...
│   │   ├── staff.py        # /staff/...
│   │   └── patients.py     # /patient/... (sign-up, login, register for a visit, cancel)
│   └── services/           # Business logic and storage
│       ├── work_orders.py  # supply_chain.db: orders, events, medicine stock
│       ├── opd.py          # opd.db: patients, tokens, events, consultations, prescriptions
│       ├── doctors.py      # doctors and their sessions
│       ├── accounts.py     # administrators, staff, patient passwords, access codes, sessions
│       ├── llm.py          # NVIDIA LLM client
│       └── seed.py         # Optional demo data
├── frontend/               # Plain HTML/CSS/JS, no build step
│   ├── index.html
│   ├── css/ (styles, doctor, accounts, admin)
│   └── js/ (main, api, ui, icons, views/*)   # login.js is the first screen; views/queue.js is part of the staff desk, not a page
├── .githooks/              # pre-push hook: runs scripts/check.py
├── scripts/
│   ├── check.py            # lint + frontend check + tests in one command (run before pushing)
│   ├── check_frontend.py   # frontend wiring check, run by CI
│   └── smoke.py            # end-to-end check against a running server, run by CI
├── .github/
│   ├── workflows/ci.yml        # checks on every push and pull request
│   └── dependabot.yml          # weekly update pull requests
├── tests/                  # pytest, 134 tests, LLM calls mocked
├── ruff.toml  requirements-dev.txt
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
5. **Add your NVIDIA key** (only needed for the summarize feature). Sign in at <https://build.nvidia.com>, open a model such as `openai/gpt-oss-20b`, click "Get API Key", and put it in `.env` as `NVIDIA_API_KEY=nvapi-...`. `.env` is git-ignored: never commit it.
6. **Start the server**
   ```bash
   uvicorn app.main:app --reload
   ```
7. **Open the app:** <http://localhost:8000> (API docs: <http://localhost:8000/docs>)
8. **Run the tests** (no internet or NVIDIA key needed)
   ```bash
   pytest
   ```

### Set up people and stock (run once, with the server stopped or running)

Create the first administrator from the command line (you are asked for a password, at least 8 characters). After that the administrator adds doctors, OPD staff and stock **from the browser** (Doctors and staff page, Dashboard).

```bash
python -m app.cli add-admin  "Dr. Rohan Mehta" ADMIN-001
```

The commands below do the same from the server, if you prefer:

```bash
python -m app.cli add-doctor "Dr. Asha Rao" MH-2026-1001 general_medicine
python -m app.cli add-staff  "Meena Joshi" OPD-001
python -m app.cli add-stock  "Paracetamol 500mg" 500
```

The Administrator dashboard shows 4 departments at a time with arrows to slide to the next 4 and a search box that filters as you type ("eye", "den", "card"). Departments (28, a multi-speciality hospital): General Medicine, Pediatrics, Gynecology & Obstetrics, Cardiology, Orthopedics, ENT, Ophthalmology (Eye), Dentistry, Dermatology, Neurology, Neurosurgery, Psychiatry, Pulmonology, Gastroenterology, Nephrology, Urology, Endocrinology, Rheumatology, Hematology, Oncology, General Surgery, Cardiothoracic Surgery, Plastic Surgery, Vascular Surgery, Infectious Disease, Geriatrics, Physiotherapy, AYUSH. Codes are in `app/schemas/opd.py`; to add one, add a line to `Department` and `DEPARTMENTS` there (no database change).

Or set `SEED_DEMO_DATA=true` in `.env` for a first start with sample data and these demo logins:

| Role | Login |
|---|---|
| Administrator | `DEMO-ADMIN` / `swasthya-admin` |
| Doctor | Dr. Asha Rao / `DEMO-1001` (more: `DEMO-1002` to `DEMO-1004`) |
| OPD staff | Meena Joshi / `DEMO-STAFF` |
| Patient | phone `9876500001` / password `careflow-demo` |

---

## How each role uses the app

Open the app and choose your role on the first screen. After you log in you see only your own pages, and **Log out** (bottom left) brings you back to the first screen. A page of another role redirects you home, and the server refuses its data (`403`) even if someone types the address.

### Administrator
1. Log in with your **admin ID and password**. Five wrong passwords in a row lock the account for a few minutes.
2. **Dashboard:** today's numbers, the live queue of every department (slide with the arrows or type in the search box), each doctor's activity, the pharmacy section, a 7-day visit chart and the live activity feed. It refreshes every few seconds.
3. **Doctors and staff:** see who can log in, who is online and what each doctor did today. Add a doctor (name, medical ID, department) or an OPD staff member (name, staff ID) with the forms. They can log in straight away.
4. **Pharmacy:** add stock (a new name creates the medicine) on the Dashboard, and run the medicine work orders (*Requested → Ordered → Received → Completed*, plus AI summary) on **Medicine stock**.
5. **Track a token** shows any token's position and wait.

### Doctor desk
1. Log in with your **name and medical ID**.
2. The dashboard shows a live count of patients waiting in **your department** (refreshes every 5 seconds).
3. **Call** the next patient. Write remarks. The patient's earlier visits (matched by phone number) appear beside the notes.
4. Search the OPD medicine list while prescribing. Each result shows live stock, and you are warned if the quantity exceeds what is in stock.
5. **Save notes** any time, or **Finish consultation** to send the patient on to the pharmacy.

### OPD staff desk
1. Log in with your **name and staff ID**.
2. **Register a walk-in patient** on the left: name, age, 10-digit phone, department, reason for visit. A token ticket appears. If the patient already has an open token, you are told which one, and nothing is created.
3. Use the department tabs and the queue board: **Call in**, **Mark prescribed**, **Send to pharmacy**, **Complete**, or **Cancel** a waiting token (for example a wrong department or a patient who left).
4. The cards above show waiting and in-consultation patients, today's registrations and completions. Below are low-stock medicines (20 units or fewer) and open medicine orders.
5. **Patient access code:** only for a patient who already has a hospital record (registered at the desk before) and wants a portal login, or forgot their password. Enter the phone number to get a 6-digit one-time code and tell it to the patient.

### Patient portal
**New patient (never registered here):**
1. **Patient portal → New here? Create your account.** Enter name, age and phone number.
2. A 6-digit code appears **on your own screen** with a 60-second countdown. Type it back and choose a password (8 or more characters). Your record and account are created and you are logged in. If the time runs out, get a new code.

**Patient who has visited before (registered at the desk):** the portal won't let anyone sign up with a phone number that already has a record, so a stranger cannot take over your history. Ask the OPD desk for a one-time code and use **Visited the hospital before?**. The same flow resets a forgotten password and logs out any older session.

**Once logged in:**
1. **Register for a visit:** see the live queue of every department (people waiting, estimated wait, who is being served), pick one, add a reason (optional) and press **Get my token**.
2. Follow your token live. While it is still *waiting* you can **Cancel** it, for example if you picked the wrong department, and register again.
3. Below, every earlier visit with the doctor's remarks and medicines. Cancelled visits are marked.

### One open token per patient
A patient is identified by phone number and can have **one** token that is not *completed* or *cancelled*, across all departments. This holds whether the patient registers themself, the desk registers them, or both press the button at the same moment: the second attempt gets `409 already_in_queue` naming the existing token. The check runs inside the same database transaction that issues the token, and a database index backs it up.

---

## Data storage

Two SQLite files in `data/`, created automatically:

| File | Contents |
|---|---|
| `supply_chain.db` | `work_orders`, `work_order_events` (every status change, timestamped), `medicines` (live stock) |
| `opd.db` | `patients` (phone number is the primary key), `opd_tokens` (one row per visit), `opd_events` (every step, timestamped, no personal data), `consultations`, `prescription_items` (prescribed and dispensed quantities), `doctors`, `staff`, `patient_accounts` (password hashes), `access_codes` (desk codes), `signup_codes` (60-second sign-up codes), `account_sessions`, `doctor_sessions` |

All times are UTC ISO-8601 with microseconds. For analysis use the `*_events` tables. **`opd.db` holds names, phone numbers and doctor remarks: do not share it.** Share exports of `opd_events` instead.

A token ends as *completed* or *cancelled*. Cancelled tokens stay in `opd_tokens` and `opd_events` for analysis but never count as waiting.

Stock rules: a work order marked *Received* adds its quantity to stock. Completing a token at the pharmacy removes the prescribed medicines from stock. If stock is short the patient gets what is available and the shortfall stays on record (`dispensed_quantity` below `quantity`).

---

## Security notes

- **Patients:** phone number plus password, stored as a salted scrypt hash.
- **Self sign-up** is allowed only for a phone number the hospital has never seen. The 60-second code on the patient's screen shows that a person (not a script) is there, but it **does not prove they own the phone number** because there is no SMS. That is why a number with an existing record needs the OPD desk's one-time code (valid 24 hours, works once, locks after 5 wrong tries).
- **Known limit:** someone could sign up with another person's number before that person ever visits. When the real owner later comes to the desk, ask for a new code: it resets the password and logs the first person out. Sending the code by SMS would close this gap completely.
- Signing up reveals whether a phone number already has a hospital record ("already registered").
- **Administrators:** admin ID plus password (scrypt hash). Five wrong passwords lock that account for a few minutes (`429`). Create the first one with `python -m app.cli add-admin`.
- **Doctors and staff:** name plus ID, no password. Anyone who knows a doctor's name and medical ID can log in as them. Add a PIN or password before real use.
- Sessions are random tokens; only their hash is stored. Administrator, staff and doctor sessions last 12 hours, patient sessions 24.
- **Who may call what** (checked on the server, not just hidden in the menu): `/admin/*`, `/work-orders` and `/summarize` are administrator-only; `/opd/*` is for OPD staff and administrators (a doctor may only move tokens of their own department and read the department queues); `/doctor/*`, `/staff/*` and `/patient/*` each need their own role. A login of the wrong role gets `403 forbidden`, no login `401`.
- There is no limit on wrong *patient* password attempts yet.
- The server speaks plain HTTP. Put it behind HTTPS (a reverse proxy) before anyone outside a trusted network uses it.
- One phone number is one patient: family members who share a phone share one record.

---

## API reference

Errors always look like:

```json
{ "error": { "code": "invalid_credentials", "message": "Name or staff ID not recognised." } }
```

Validation errors (`422`) add a `details` list of `{field, message}`. Logged-in endpoints expect `Authorization: Bearer <token>` from the matching login. Medicine work orders and the `/opd/...` endpoints below need an administrator (and, for `/opd`, OPD staff) token.

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
| `POST` | `/opd/tokens` | Register a patient (`phone`: exactly 10 digits), get a token such as `GM-004`. `409 already_in_queue` if they already have an open token |
| `GET` | `/opd/tokens?department=&status=` | List tokens |
| `GET` | `/opd/tokens/{token}` | One token with `position` and `estimated_wait_minutes` |
| `PATCH` | `/opd/tokens/{token}/status` | Advance one step (`409 doctor_busy` if the doctor has someone in), or set `cancelled` while still `waiting` |
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

### Administrator
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/admin/login` | `{admin_id, password}` returns a token (`401 invalid_credentials`, `429 too_many_attempts`) |
| `POST` | `/admin/logout` | End the session |
| `GET` | `/admin/dashboard` | Today, totals, 7-day visits, department queues, every doctor's activity, staff, pharmacy, live feed |
| `POST` | `/admin/doctors` | `{name, medical_id, department}` register a doctor (`409 already_registered`) |
| `POST` | `/admin/staff` | `{name, staff_id}` register OPD staff (`409 already_registered`) |
| `POST` | `/admin/stock` | `{medicine, quantity}` add stock, creating the medicine if new |

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
| `POST` | `/patient/signup/start` | New patient: `{phone, name, age}` returns a 6-digit `code` and `expires_in_seconds: 60` (`409 phone_already_registered`) |
| `POST` | `/patient/signup` | `{phone, code, password}` creates the record and account, logs in (`401 invalid_code`) |
| `POST` | `/patient/activate` | Existing patient: `{phone, code, password}` with the OPD desk's code sets or resets the password |
| `POST` | `/patient/login` | `{phone, password}` returns a token (`401 invalid_credentials`) |
| `POST` | `/patient/logout` | End the session |
| `GET` | `/patient/dashboard` | Live token, live queue of every department, all visits with remarks and medicines |
| `POST` | `/patient/tokens` | `{department, complaint?}` take a token for yourself (`409 already_in_queue`) |
| `POST` | `/patient/tokens/cancel` | Cancel your own token while it is waiting (`409` once the visit has started, `404 no_open_visit`) |

---

## CI (GitHub Actions)

Every push to `main` and every pull request runs four checks on GitHub, so you find out **before merging** what is broken. Results show as green ticks or red crosses on the pull request, and GitHub emails you when something fails.

| Job | What it catches |
|---|---|
| **Lint and wiring checks** | Unused or undefined names and bug-prone Python (`ruff`), JavaScript syntax errors, imports of files that don't exist, menu links without a route, missing CSS/JS files, and a committed `.env`, database file or NVIDIA key |
| **Tests** (4 runs) | The 134 tests on **Python 3.10 and 3.13, on Linux and on Windows**. One failing combination never hides the others |
| **Smoke test** | Starts the real server with demo data and drives it over HTTP: all page files load, administrator, doctor, staff and patient can log in, the administrator dashboard loads and a doctor's token is refused there, walk-in registration, patient sign-up and self-registration, and the one-open-token rule between the desk and the patient |
| **Dependency scan** | Known vulnerabilities in the libraries. Informational only: it warns but never blocks |
| **CI passed** | One summary check. Make **this** the required check (below) |

The checks also run **every Monday morning**. `requirements.txt` does not pin versions, so a new release of FastAPI or Pydantic can break the app while nobody touched the code. The Monday run tells you.

### Switch it on, step by step

1. **Put the project in git** (from the `careflow` folder). `.gitignore` already keeps `.env`, `data/` and `venv/` out.
   ```bash
   git init -b main
   git add .
   git status                 # check that .env, data/ and venv/ are NOT listed
   git commit -m "Swasthya AI"
   ```
2. **Create an empty repository** on GitHub (no README, no .gitignore), then connect and push:
   ```bash
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. Open the **Actions** tab. The first run starts by itself.
4. **Require the check before merging** (so a red build can't reach `main`): *Settings → Branches → Add branch ruleset (or protection rule)* for `main` → require a pull request → *Require status checks* → add **CI passed**.
5. Work through branches and pull requests:
   ```bash
   git switch -c my-change
   # ...edit, commit...
   git push -u origin my-change     # then open a pull request on GitHub
   ```

### Run the same checks on your own computer first (before every push)

```bash
pip install -r requirements-dev.txt
python scripts/check.py        # lint, frontend wiring, tests: the same as CI, in about 10 seconds
```

To make Git run it for you automatically on every `git push`, turn on the bundled hook once:

```bash
git config core.hooksPath .githooks
```

From then on a failing check prints its error in your terminal and **stops the push**. (Skip it for one push with `git push --no-verify`.) The slower smoke test is run by GitHub only; to run it yourself, start the server with `SEED_DEMO_DATA=true` on an empty data folder and run `python scripts/smoke.py http://127.0.0.1:8000`.

### Seeing the result of a push

GitHub runs CI on its own servers after the push, so nothing appears in the terminal by itself. Ways to see it:

- **Actions tab** of your repository: every push is a row, with a green tick, a red cross or a yellow dot (running).
- **On the commit or pull request:** the same status shows next to it, and a pull request lists each check.
- **Email:** GitHub emails you when a run you triggered fails (Settings, Notifications, Actions).
- **Terminal, optional:** with the [GitHub CLI](https://cli.github.com) installed and `gh auth login` done, run `gh run watch` right after pushing to follow the run live, or `gh run list --limit 5` for the latest results.

### Reading a failure
Open the failed run, click the red job, and expand the red step. The message names the file and the problem, for example *"index.html has a menu link data-route="staffdesk" but main.js has no such route"*. If the smoke test fails, its last step prints the server log.

### Deployment (not included)
This pipeline only checks the code (CI). Automatic release and deployment (CD) are deliberately left out until you choose where the app will run. Until then, run it as described in *Run it, step by step*.

### What the pipeline does not do (yet)
It does not drive a real browser, so a purely visual bug (a button that looks wrong) is not caught. Adding Playwright browser tests is the natural next step.

---

## Design decisions (YAGNI)

Built because the brief needs it: the workflows, validation, structured errors, SQLite storage, three role logins and dashboards.
Left out until there is a real need:

- **Passwords for doctors and staff**, SMS or email codes, rate limiting, roles and permissions beyond "doctor / staff / patient".
- **Protecting the open endpoints** behind the staff desk (`/opd/...`, `/work-orders`). Next step: require the staff or doctor login.
- **Migrations tool.** New tables are created automatically on start (`CREATE TABLE IF NOT EXISTS`); existing tables are never altered.
- **ORM, pagination, frontend framework, build step.** Plain `sqlite3` and ES modules are enough at this size.
- **Daily token reset, automatic no-show handling, cancelling after the visit has started, editing a patient's phone number.**

## Roadmap

1. Require login on the queue and stock endpoints, and add a PIN for doctors.
2. Reset token numbers each day; handle no-shows.
3. Reporting from the `*_events` tables: waiting time per department, stock-out frequency, time to replenish.
4. Send codes by SMS, which also lets new patients prove they own their phone number.
5. Integration with existing hospital systems (HL7/FHIR or the hospital's HIS API).
6. Walk registration, pharmacy and doctors through the flows and adjust wording and departments.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `NVIDIA_API_KEY` | none | NVIDIA key for `/summarize` |
| `NVIDIA_MODEL` | `openai/gpt-oss-20b` | Any chat model with a Free Endpoint badge on build.nvidia.com |
| `AVG_CONSULT_MINUTES` | `10` | Used for the estimated wait |
| `SEED_DEMO_DATA` | `false` | Load sample data on the **first** start only (empty databases) |
| `DATA_DIR` | `data` | Folder for the two database files |
