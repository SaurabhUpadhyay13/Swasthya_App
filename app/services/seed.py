"""Optional demo data (SEED_DEMO_DATA=true) so the dashboard is not empty on first run."""

from app.schemas.opd import Department, PatientRegistration, TokenStatus
from app.schemas.work_orders import Priority, WorkOrderCreate, WorkOrderStatus
from app.services.opd import OpdStore
from app.services.work_orders import WorkOrderStore

_ORDERS = [
    ("Paracetamol 500mg", 2000, Priority.critical, "Pharmacy ran out this morning; 40 OPD prescriptions for fever cases are pending.", 0),
    ("Amoxicillin 250mg", 800, Priority.high, "Paediatric stock below safe level after a surge in respiratory infections.", 1),
    ("Insulin Glargine", 120, Priority.critical, "Cold-chain shipment delayed; only two days of stock left for diabetic outpatients.", 2),
    ("Normal Saline 500ml", 600, Priority.medium, "Routine top-up ahead of the weekend; ward stock is at 30%.", 3),
    ("Surgical Gloves (M)", 50, Priority.low, "Monthly consumables restock for the minor procedure room.", 3),
]

_PATIENTS = [
    ("Asha Verma", 34, "9876500001", Department.general_medicine, "Fever for 3 days"),
    ("Ravi Kumar", 58, "9876500002", Department.general_medicine, "Persistent cough"),
    ("Meera Nair", 41, "9876500003", Department.general_medicine, "Headache and nausea"),
    ("Imran Sheikh", 7, "9876500004", Department.pediatrics, "Ear pain"),
    ("Sunita Rao", 62, "9876500005", Department.cardiology, "Chest discomfort on exertion"),
    ("Arjun Patel", 29, "9876500006", Department.orthopedics, "Knee pain after fall"),
]

# OPD medicine list with opening stock (Amoxicillin is out of stock on purpose, to show the warning).
_STOCK = [("Paracetamol 500mg", 400), ("Cetirizine 10mg", 120), ("Insulin Glargine", 15), ("ORS Sachet", 300)]


def seed_demo_data(orders: WorkOrderStore, opd: OpdStore) -> None:
    if orders.list_orders() or opd.list_tokens():
        return  # never mix demo rows into a database that already holds data
    flow = [WorkOrderStatus.ordered, WorkOrderStatus.received, WorkOrderStatus.completed]
    for name, qty, priority, description, steps in _ORDERS:
        order = orders.create(
            WorkOrderCreate(medicine_name=name, quantity_needed=qty, priority=priority, description=description)
        )
        for status in flow[:steps]:
            orders.update_status(order.id, status)

    for name, quantity in _STOCK:
        orders.add_stock(name, quantity)
    # Demo login on the Doctor desk: Dr. Asha Rao / DEMO-1001
    opd.doctors.add("Dr. Asha Rao", "DEMO-1001", Department.general_medicine)
    # Demo login on the Staff desk: Meena Joshi / DEMO-STAFF
    opd.staff.add("Meena Joshi", "DEMO-STAFF")

    tokens = [
        opd.register(PatientRegistration(patient_name=n, age=a, phone=p, department=d, complaint=c))
        for n, a, p, d, c in _PATIENTS
    ]
    # Demo login on the Patient portal: phone 9876500001 / password careflow-demo
    opd.patient_accounts.set_password("9876500001", "careflow-demo")
    opd.update_status(tokens[0].token, TokenStatus.in_consultation)  # GM-001 is being seen
    opd.update_status(tokens[3].token, TokenStatus.in_consultation)  # PD-001 is being seen
