"""
Patient Intake Database Schema
Supports patient info, visit history, and change audit logging.
"""

SCHEMA = """
-- =============================================================================
-- 1. PATIENTS - Core patient information
-- =============================================================================
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,

    -- Patient Info
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,

    -- Address (validated via Google Maps API)
    address_line1 TEXT,
    address_line2 TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    address_validated INTEGER DEFAULT 0,

    -- Insurance Info
    insurance_payer TEXT,
    insurance_plan TEXT,
    insurance_member_id TEXT,
    insurance_group_id TEXT,

    -- Metadata
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patients_phone ON patients(phone);
CREATE INDEX IF NOT EXISTS idx_patients_email ON patients(email);
CREATE INDEX IF NOT EXISTS idx_patients_name_dob ON patients(last_name, first_name, date_of_birth);


-- =============================================================================
-- 2. PATIENT_CHANGE_LOG - Audit trail for patient info changes
-- =============================================================================
CREATE TABLE IF NOT EXISTS patient_change_log (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_type TEXT NOT NULL,
    changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_change_log_patient ON patient_change_log(patient_id);
CREATE INDEX IF NOT EXISTS idx_change_log_time ON patient_change_log(changed_at);


-- =============================================================================
-- 3. VISITS - Patient visit history (chief complaints/reasons)
-- =============================================================================
CREATE TABLE IF NOT EXISTS visits (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,

    -- Visit details
    chief_complaint TEXT NOT NULL,
    symptoms TEXT,
    symptom_duration TEXT,
    severity INTEGER,

    -- Status tracking
    status TEXT DEFAULT 'pending',

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,

    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE INDEX IF NOT EXISTS idx_visits_patient ON visits(patient_id);
CREATE INDEX IF NOT EXISTS idx_visits_status ON visits(status);


-- =============================================================================
-- 4. PROVIDERS - Healthcare providers with embedded availability
-- =============================================================================
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,

    -- Insurance accepted (JSON array: ["Blue Cross PPO", "Aetna HMO"])
    insurance_accepted TEXT,

    -- Conditions treated (JSON array: ["back pain", "sports injuries"])
    conditions_treated TEXT,

    -- Rating
    rating REAL DEFAULT 0.0,

    -- Embedded schedule
    available_days TEXT,  -- JSON array: ["Monday", "Wednesday", "Friday"]
    hours_start TEXT,     -- "09:00"
    hours_end TEXT,       -- "17:00"

    -- Metadata
    accepting_new_patients INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_providers_specialty ON providers(specialty);


-- =============================================================================
-- 5. APPOINTMENTS - Combines slots and bookings
-- =============================================================================
-- When patient_id is NULL, it's an available slot
-- When patient_id is filled, it's a booked appointment
CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    patient_id TEXT,
    visit_id TEXT,

    -- Scheduling
    date TEXT NOT NULL,
    time TEXT NOT NULL,

    -- Status: available, booked, completed, cancelled, no_show
    status TEXT DEFAULT 'available',

    -- Booking details (filled when booked)
    reason TEXT,
    notes TEXT,

    -- Timestamps
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    booked_at TEXT,

    FOREIGN KEY (provider_id) REFERENCES providers(id),
    FOREIGN KEY (patient_id) REFERENCES patients(id),
    FOREIGN KEY (visit_id) REFERENCES visits(id)
);

CREATE INDEX IF NOT EXISTS idx_appointments_provider ON appointments(provider_id);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
"""
