"""Seed the database with mock patient, provider, and appointment data."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from patient_intake.database import init_database, PatientRepository, get_connection
from patient_intake.database.patient_repository import Patient


MOCK_PATIENTS = [
    Patient(
        id="p-001",
        first_name="John",
        last_name="Smith",
        date_of_birth="1985-03-15",
        phone="555-0101",
        email="john.smith@email.com",
        address_line1="123 Main St",
        address_line2="Apt 4B",
        city="San Francisco",
        state="CA",
        zip_code="94102",
        address_validated=True,
        insurance_payer="Blue Cross Blue Shield",
        insurance_plan="PPO",
        insurance_member_id="BCBS123456",
        insurance_group_id="GRP001",
    ),
    Patient(
        id="p-002",
        first_name="Sarah",
        last_name="Johnson",
        date_of_birth="1992-07-22",
        phone="555-0102",
        email="sarah.j@email.com",
        address_line1="456 Oak Ave",
        city="Oakland",
        state="CA",
        zip_code="94612",
        address_validated=True,
        insurance_payer="Aetna",
        insurance_plan="HMO",
        insurance_member_id="AET789012",
    ),
    Patient(
        id="p-003",
        first_name="Michael",
        last_name="Chen",
        date_of_birth="1978-11-08",
        phone="555-0103",
        email="m.chen@email.com",
        address_line1="789 Pine Rd",
        city="Berkeley",
        state="CA",
        zip_code="94704",
        address_validated=False,
        insurance_payer="Kaiser Permanente",
        insurance_plan="HMO",
        insurance_member_id="KP345678",
        insurance_group_id="GRP002",
    ),
    Patient(
        id="p-004",
        first_name="Emily",
        last_name="Davis",
        date_of_birth="2000-01-30",
        phone="555-0104",
        email="emily.d@email.com",
        address_line1="321 Elm St",
        city="San Jose",
        state="CA",
        zip_code="95110",
        address_validated=True,
    ),
    Patient(
        id="p-005",
        first_name="Robert",
        last_name="Wilson",
        date_of_birth="1965-09-12",
        phone="555-0105",
        address_line1="654 Cedar Ln",
        city="Palo Alto",
        state="CA",
        zip_code="94301",
        address_validated=True,
        insurance_payer="Medicare",
        insurance_plan="Part B",
        insurance_member_id="MED901234",
    ),
]

MOCK_VISITS = [
    ("p-001", "Back pain", '["lower back pain", "stiffness"]', "2 weeks", 6),
    ("p-001", "Annual physical", None, None, None),
    ("p-001", "Follow-up for back pain", '["improved mobility"]', "1 month", 3),
    ("p-002", "Headache and fatigue", '["headache", "fatigue", "difficulty concentrating"]', "3 days", 5),
    ("p-002", "Flu symptoms", '["fever", "cough", "body aches"]', "2 days", 7),
    ("p-003", "Knee injury", '["swelling", "pain when walking"]', "1 week", 8),
    ("p-003", "Physical therapy follow-up", '["improved range of motion"]', "3 weeks", 4),
    ("p-004", "Skin rash", '["itching", "redness"]', "5 days", 4),
    ("p-005", "Chest discomfort", '["mild chest pain", "shortness of breath"]', "2 days", 7),
    ("p-005", "Diabetes management", None, "ongoing", 3),
]

MOCK_PROVIDERS = [
    {
        "id": "prov-001",
        "name": "Dr. Sarah Chen",
        "specialty": "Family Medicine",
        "address": "123 Medical Center Dr, San Francisco, CA 94102",
        "phone": "415-555-0201",
        "email": "dr.chen@medical.com",
        "insurance_accepted": '["Blue Cross Blue Shield PPO", "Aetna HMO", "Kaiser Permanente HMO"]',
        "conditions_treated": '["general checkup", "cold/flu", "chronic conditions", "preventive care", "back pain"]',
        "rating": 4.8,
        "available_days": '["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]',
        "hours_start": "09:00",
        "hours_end": "17:00",
    },
    {
        "id": "prov-002",
        "name": "Dr. Michael Roberts",
        "specialty": "Internal Medicine",
        "address": "456 Health Plaza, Oakland, CA 94612",
        "phone": "510-555-0202",
        "email": "dr.roberts@health.com",
        "insurance_accepted": '["Kaiser Permanente HMO", "Blue Cross Blue Shield PPO", "Medicare Part B"]',
        "conditions_treated": '["diabetes", "hypertension", "heart health", "general checkup", "chest discomfort"]',
        "rating": 4.6,
        "available_days": '["Monday", "Wednesday", "Friday"]',
        "hours_start": "08:00",
        "hours_end": "16:00",
    },
    {
        "id": "prov-003",
        "name": "Dr. Emily Watson",
        "specialty": "Dermatology",
        "address": "789 Skin Care Blvd, San Jose, CA 95110",
        "phone": "408-555-0203",
        "email": "dr.watson@derma.com",
        "insurance_accepted": '["Aetna HMO", "Blue Cross Blue Shield PPO", "United Healthcare"]',
        "conditions_treated": '["skin rash", "acne", "eczema", "skin cancer screening", "cosmetic dermatology"]',
        "rating": 4.9,
        "available_days": '["Tuesday", "Thursday"]',
        "hours_start": "10:00",
        "hours_end": "18:00",
    },
    {
        "id": "prov-004",
        "name": "Dr. James Park",
        "specialty": "Orthopedics",
        "address": "321 Bone & Joint Center, Berkeley, CA 94704",
        "phone": "510-555-0204",
        "email": "dr.park@ortho.com",
        "insurance_accepted": '["Kaiser Permanente HMO", "Aetna HMO", "Medicare Part B"]',
        "conditions_treated": '["knee injury", "back pain", "sports injuries", "arthritis", "fractures"]',
        "rating": 4.7,
        "available_days": '["Monday", "Tuesday", "Thursday", "Friday"]',
        "hours_start": "09:00",
        "hours_end": "17:00",
    },
    {
        "id": "prov-005",
        "name": "Dr. Lisa Martinez",
        "specialty": "Neurology",
        "address": "654 Brain Health Center, Palo Alto, CA 94301",
        "phone": "650-555-0205",
        "email": "dr.martinez@neuro.com",
        "insurance_accepted": '["Blue Cross Blue Shield PPO", "Medicare Part B", "United Healthcare"]',
        "conditions_treated": '["headache", "migraine", "fatigue", "neurological disorders", "memory issues"]',
        "rating": 4.5,
        "available_days": '["Wednesday", "Thursday", "Friday"]',
        "hours_start": "08:30",
        "hours_end": "16:30",
    },
]


def generate_appointment_slots(provider_id: str, start_date: datetime, days: int = 14) -> list:
    """Generate available appointment slots for a provider."""
    slots = []
    current = start_date

    for _ in range(days):
        date_str = current.strftime("%Y-%m-%d")
        # Generate slots from 9am to 5pm, every 30 minutes
        for hour in range(9, 17):
            for minute in [0, 30]:
                slot_id = f"slot-{provider_id}-{date_str}-{hour:02d}{minute:02d}"
                slots.append({
                    "id": slot_id,
                    "provider_id": provider_id,
                    "date": date_str,
                    "time": f"{hour:02d}:{minute:02d}",
                    "status": "available",
                })
        current += timedelta(days=1)

    return slots


def seed_database():
    """Initialize and seed the database with mock data."""
    print("Initializing database...")
    init_database()

    conn = get_connection()
    cursor = conn.cursor()
    repo = PatientRepository()

    # Seed patients
    print("Creating mock patients...")
    for patient in MOCK_PATIENTS:
        existing = repo.get_by_id(patient.id)
        if existing:
            print(f"  Skipping {patient.first_name} {patient.last_name} (already exists)")
        else:
            repo.create(patient, changed_by="seed_script")
            print(f"  Created {patient.first_name} {patient.last_name}")

    # Seed visits
    print("Creating mock visits...")
    for patient_id, complaint, symptoms, duration, severity in MOCK_VISITS:
        repo.create_visit(
            patient_id=patient_id,
            chief_complaint=complaint,
            symptoms=symptoms,
            symptom_duration=duration,
            severity=severity
        )
        print(f"  Created visit: {complaint[:30]}...")

    # Seed providers
    print("Creating mock providers...")
    for provider in MOCK_PROVIDERS:
        cursor.execute("SELECT id FROM providers WHERE id = ?", (provider["id"],))
        if cursor.fetchone():
            print(f"  Skipping {provider['name']} (already exists)")
        else:
            cursor.execute(
                """INSERT INTO providers
                   (id, name, specialty, address, phone, email,
                    insurance_accepted, conditions_treated, rating,
                    available_days, hours_start, hours_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    provider["id"],
                    provider["name"],
                    provider["specialty"],
                    provider["address"],
                    provider["phone"],
                    provider["email"],
                    provider["insurance_accepted"],
                    provider["conditions_treated"],
                    provider["rating"],
                    provider["available_days"],
                    provider["hours_start"],
                    provider["hours_end"],
                ),
            )
            print(f"  Created {provider['name']}")

    # Seed appointment slots (next 14 days)
    print("Creating appointment slots...")
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total_slots = 0

    for provider in MOCK_PROVIDERS:
        # Check if slots already exist for this provider
        cursor.execute(
            "SELECT COUNT(*) FROM appointments WHERE provider_id = ?",
            (provider["id"],)
        )
        existing_count = cursor.fetchone()[0]
        if existing_count > 0:
            print(f"  Skipping slots for {provider['name']} ({existing_count} already exist)")
            continue

        slots = generate_appointment_slots(provider["id"], start_date)
        for slot in slots:
            cursor.execute(
                """INSERT INTO appointments (id, provider_id, date, time, status)
                   VALUES (?, ?, ?, ?, ?)""",
                (slot["id"], slot["provider_id"], slot["date"], slot["time"], slot["status"]),
            )
        total_slots += len(slots)
        print(f"  Created {len(slots)} slots for {provider['name']}")

    conn.commit()
    conn.close()

    print("\nDatabase seeded successfully!")
    print(f"  - {len(MOCK_PATIENTS)} patients")
    print(f"  - {len(MOCK_VISITS)} visits")
    print(f"  - {len(MOCK_PROVIDERS)} providers")
    print(f"  - {total_slots} appointment slots")


if __name__ == "__main__":
    seed_database()
