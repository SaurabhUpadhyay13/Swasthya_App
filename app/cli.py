"""Administrator commands. Run from the project folder with the virtual environment active.

Register an administrator (they log in on the Admin screen with this ID and a password; you are asked for it):

    python -m app.cli add-admin "Dr. Rohan Mehta" ADMIN-001

Register a doctor (they can then log in on the Doctor desk with this name and medical ID):

    python -m app.cli add-doctor "Dr. Asha Rao" MH-2026-1001 general_medicine

Register OPD staff (they can then log in on the Staff desk with this name and staff ID):

    python -m app.cli add-staff "Meena Joshi" OPD-001

Add medicine to the OPD stock (an opening balance, or a manual top-up):

    python -m app.cli add-stock "Paracetamol 500mg" 500

Department codes: see app/schemas/opd.py (for example general_medicine, cardiology, ophthalmology, dentistry)
"""

import argparse
import getpass

from app.config import get_settings
from app.schemas.opd import DEPARTMENTS, Department
from app.services.opd import get_opd_store
from app.services.work_orders import get_work_order_store


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Swasthya AI administrator commands")
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("add-admin", help="Register an administrator who can log in")
    admin.add_argument("name", help='Full name, e.g. "Dr. Rohan Mehta"')
    admin.add_argument("admin_id", help="Admin ID, e.g. ADMIN-001")
    admin.add_argument("--password", help="At least 8 characters. Leave out to be asked (keeps it out of your shell history)")

    doctor = commands.add_parser("add-doctor", help="Register a doctor who can log in")
    doctor.add_argument("name", help='Full name, e.g. "Dr. Asha Rao"')
    doctor.add_argument("medical_id", help="Registered medical ID, e.g. MH-2026-1001")
    doctor.add_argument("department", choices=[d.value for d in Department])

    staff = commands.add_parser("add-staff", help="Register an OPD staff member who can log in")
    staff.add_argument("name", help='Full name, e.g. "Meena Joshi"')
    staff.add_argument("staff_id", help="Staff ID, e.g. OPD-001")

    stock = commands.add_parser("add-stock", help="Add medicine to the OPD stock")
    stock.add_argument("medicine", help='Medicine name, e.g. "Paracetamol 500mg"')
    stock.add_argument("quantity", type=int, help="How many to add (a positive number)")

    args = parser.parse_args()
    settings = get_settings()
    supply = get_work_order_store(settings)
    opd = get_opd_store(settings, supply)

    if args.command == "add-admin":
        password = args.password or getpass.getpass("Password (at least 8 characters): ")
        try:
            person = opd.admins.add(args.name, args.admin_id, password)
        except ValueError as error:
            parser.exit(1, f"Error: {error}\n")
        print(f"Registered {person.name} (admin ID {person.admin_id}).")
    elif args.command == "add-doctor":
        try:
            doctor = opd.doctors.add(args.name, args.medical_id, Department(args.department))
        except ValueError as error:
            parser.exit(1, f"Error: {error}\n")
        print(f"Registered {doctor.name} (medical ID {doctor.medical_id}) in {DEPARTMENTS[doctor.department][0]}.")
    elif args.command == "add-staff":
        try:
            member = opd.staff.add(args.name, args.staff_id)
        except ValueError as error:
            parser.exit(1, f"Error: {error}\n")
        print(f"Registered {member.name} (staff ID {member.staff_id}).")
    else:
        if args.quantity <= 0:
            parser.exit(1, "Error: quantity must be a positive number.\n")
        supply.add_stock(args.medicine, args.quantity)
        print(f"Added {args.quantity} to {' '.join(args.medicine.split())}.")


if __name__ == "__main__":
    main()
