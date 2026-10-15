from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Department(str, Enum):
    general_medicine = "general_medicine"
    pediatrics = "pediatrics"
    gynecology = "gynecology"
    cardiology = "cardiology"
    orthopedics = "orthopedics"
    ent = "ent"
    ophthalmology = "ophthalmology"
    dentistry = "dentistry"
    dermatology = "dermatology"
    neurology = "neurology"
    neurosurgery = "neurosurgery"
    psychiatry = "psychiatry"
    pulmonology = "pulmonology"
    gastroenterology = "gastroenterology"
    nephrology = "nephrology"
    urology = "urology"
    endocrinology = "endocrinology"
    rheumatology = "rheumatology"
    hematology = "hematology"
    oncology = "oncology"
    general_surgery = "general_surgery"
    cardiothoracic_surgery = "cardiothoracic_surgery"
    plastic_surgery = "plastic_surgery"
    vascular_surgery = "vascular_surgery"
    infectious_disease = "infectious_disease"
    geriatrics = "geriatrics"
    physiotherapy = "physiotherapy"
    ayush = "ayush"


# code -> (display name, token prefix). Prefixes must be unique: they start every token number.
DEPARTMENTS: dict[Department, tuple[str, str]] = {
    Department.general_medicine: ("General Medicine", "GM"),
    Department.pediatrics: ("Pediatrics", "PD"),
    Department.gynecology: ("Gynecology & Obstetrics", "GY"),
    Department.cardiology: ("Cardiology", "CD"),
    Department.orthopedics: ("Orthopedics", "OR"),
    Department.ent: ("ENT", "EN"),
    Department.ophthalmology: ("Ophthalmology (Eye)", "EY"),
    Department.dentistry: ("Dentistry", "DN"),
    Department.dermatology: ("Dermatology (Skin)", "DM"),
    Department.neurology: ("Neurology", "NR"),
    Department.neurosurgery: ("Neurosurgery", "NS"),
    Department.psychiatry: ("Psychiatry", "PS"),
    Department.pulmonology: ("Pulmonology (Chest)", "PM"),
    Department.gastroenterology: ("Gastroenterology", "GE"),
    Department.nephrology: ("Nephrology (Kidney)", "NP"),
    Department.urology: ("Urology", "UR"),
    Department.endocrinology: ("Endocrinology (Diabetes)", "EC"),
    Department.rheumatology: ("Rheumatology", "RH"),
    Department.hematology: ("Hematology", "HM"),
    Department.oncology: ("Oncology (Cancer)", "ON"),
    Department.general_surgery: ("General Surgery", "SG"),
    Department.cardiothoracic_surgery: ("Cardiothoracic Surgery", "CT"),
    Department.plastic_surgery: ("Plastic Surgery", "PL"),
    Department.vascular_surgery: ("Vascular Surgery", "VS"),
    Department.infectious_disease: ("Infectious Disease", "ID"),
    Department.geriatrics: ("Geriatrics", "GR"),
    Department.physiotherapy: ("Physiotherapy & Rehab", "PT"),
    Department.ayush: ("AYUSH", "AY"),
}


class TokenStatus(str, Enum):
    waiting = "waiting"
    in_consultation = "in_consultation"
    prescribed = "prescribed"
    pharmacy = "pharmacy"
    completed = "completed"
    cancelled = "cancelled"  # only from waiting; never part of the forward flow


# Registration -> Token -> Queue -> Consultation -> Prescription -> Pharmacy
TOKEN_FLOW = (
    TokenStatus.waiting,
    TokenStatus.in_consultation,
    TokenStatus.prescribed,
    TokenStatus.pharmacy,
    TokenStatus.completed,
)


class PatientRegistration(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    patient_name: str = Field(min_length=2, max_length=100, examples=["Asha Verma"])
    age: int = Field(ge=0, le=120, examples=[34])
    # The phone number is the patient's permanent ID across visits, so it is required.
    # Exactly 10 digits (no +91, spaces or dashes) keeps one patient from getting two IDs.
    phone: str = Field(pattern=r"^\d{10}$", examples=["9876543210"])
    department: Department
    complaint: str | None = Field(default=None, max_length=300, examples=["Fever for 3 days"])


class TokenStatusUpdate(BaseModel):
    status: TokenStatus


class Token(BaseModel):
    token: str = Field(examples=["GM-007"])
    sequence: int
    patient_name: str
    age: int
    # No phone number here: these endpoints are open, and the phone is the patient's identity.
    department: Department
    department_name: str
    complaint: str | None
    status: TokenStatus
    registered_at: datetime
    updated_at: datetime
    # Only meaningful while status == waiting
    position: int | None = Field(default=None, description="1 = next to be called.")
    estimated_wait_minutes: int | None = None


class DepartmentQueue(BaseModel):
    code: Department
    name: str
    prefix: str
    now_serving: str | None
    waiting: int
