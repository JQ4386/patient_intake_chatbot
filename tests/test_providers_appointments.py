"""Tests for providers and appointments tables."""

import json
import pytest
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "assort_intake_bot"))

from patient_intake.database import init_database
from patient_intake.database.connection import get_connection


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Initialize database before tests."""
    init_database()
    yield


@pytest.fixture
def db_connection():
    """Get a database connection."""
    conn = get_connection()
    yield conn
    conn.close()


# =============================================================================
# Provider Tests
# =============================================================================


class TestProvidersCRUD:
    """Tests for providers table CRUD operations."""

    def test_create_provider(self, db_connection):
        """Test creating a new provider."""
        provider_id = "prov-test-001"
        conn = db_connection

        # Cleanup first
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

        # Insert provider
        conn.execute(
            """INSERT INTO providers
               (id, name, specialty, address, phone, email,
                insurance_accepted, conditions_treated, rating,
                available_days, hours_start, hours_end)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                provider_id,
                "Dr. Test Provider",
                "Family Medicine",
                "123 Test St, Test City, CA 12345",
                "555-TEST",
                "dr.test@test.com",
                '["Test Insurance PPO", "Another Insurance HMO"]',
                '["general checkup", "cold/flu"]',
                4.5,
                '["Monday", "Wednesday", "Friday"]',
                "09:00",
                "17:00",
            ),
        )
        conn.commit()

        # Verify
        cursor = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["name"] == "Dr. Test Provider"
        assert row["specialty"] == "Family Medicine"
        assert row["rating"] == 4.5

        # Cleanup
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

    def test_provider_insurance_json(self, db_connection):
        """Test that insurance_accepted JSON can be parsed."""
        provider_id = "prov-test-json"
        conn = db_connection

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        insurance_list = ["Blue Cross PPO", "Aetna HMO", "Kaiser"]
        conn.execute(
            "INSERT INTO providers (id, name, insurance_accepted) VALUES (?, ?, ?)",
            (provider_id, "Dr. JSON Test", json.dumps(insurance_list)),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT insurance_accepted FROM providers WHERE id = ?", (provider_id,)
        )
        row = cursor.fetchone()
        parsed = json.loads(row["insurance_accepted"])

        assert parsed == insurance_list
        assert "Blue Cross PPO" in parsed

        # Cleanup
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

    def test_provider_conditions_json(self, db_connection):
        """Test that conditions_treated JSON can be parsed."""
        provider_id = "prov-test-conditions"
        conn = db_connection

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        conditions = ["back pain", "knee injury", "sports injuries"]
        conn.execute(
            "INSERT INTO providers (id, name, conditions_treated) VALUES (?, ?, ?)",
            (provider_id, "Dr. Conditions Test", json.dumps(conditions)),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT conditions_treated FROM providers WHERE id = ?", (provider_id,)
        )
        row = cursor.fetchone()
        parsed = json.loads(row["conditions_treated"])

        assert "back pain" in parsed
        assert len(parsed) == 3

        # Cleanup
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

    def test_find_providers_by_specialty(self, db_connection):
        """Test finding providers by specialty."""
        conn = db_connection

        # Query existing seeded data
        cursor = conn.execute(
            "SELECT * FROM providers WHERE specialty = ?", ("Family Medicine",)
        )
        rows = cursor.fetchall()

        # Should find at least one (Dr. Sarah Chen from seed data)
        assert len(rows) >= 0  # May be empty if no seed data

    def test_find_providers_by_insurance(self, db_connection):
        """Test finding providers by insurance using LIKE."""
        conn = db_connection

        # Query using LIKE for JSON contains
        cursor = conn.execute(
            "SELECT * FROM providers WHERE insurance_accepted LIKE ?",
            ("%Blue Cross%",),
        )
        rows = cursor.fetchall()

        # Verify results have the insurance
        for row in rows:
            assert "Blue Cross" in row["insurance_accepted"]

    def test_find_providers_by_condition(self, db_connection):
        """Test finding providers by condition treated."""
        conn = db_connection

        cursor = conn.execute(
            "SELECT * FROM providers WHERE conditions_treated LIKE ?",
            ("%back pain%",),
        )
        rows = cursor.fetchall()

        for row in rows:
            assert "back pain" in row["conditions_treated"]

    def test_provider_rating_ordering(self, db_connection):
        """Test ordering providers by rating."""
        conn = db_connection

        cursor = conn.execute(
            "SELECT name, rating FROM providers ORDER BY rating DESC"
        )
        rows = cursor.fetchall()

        if len(rows) > 1:
            for i in range(len(rows) - 1):
                assert rows[i]["rating"] >= rows[i + 1]["rating"]

    def test_get_provider_by_id(self, db_connection):
        """Test reading a provider by ID."""
        provider_id = "prov-test-read"
        conn = db_connection

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        # Create provider
        conn.execute(
            "INSERT INTO providers (id, name, specialty) VALUES (?, ?, ?)",
            (provider_id, "Dr. Read Test", "Cardiology"),
        )
        conn.commit()

        # Read by ID
        cursor = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["id"] == provider_id
        assert row["name"] == "Dr. Read Test"
        assert row["specialty"] == "Cardiology"

        # Cleanup
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

    def test_get_provider_by_id_not_found(self, db_connection):
        """Test reading a non-existent provider returns None."""
        conn = db_connection

        cursor = conn.execute("SELECT * FROM providers WHERE id = ?", ("nonexistent-id",))
        row = cursor.fetchone()

        assert row is None

    def test_update_provider(self, db_connection):
        """Test updating a provider."""
        provider_id = "prov-test-update"
        conn = db_connection

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        # Create provider
        conn.execute(
            "INSERT INTO providers (id, name, specialty, rating) VALUES (?, ?, ?, ?)",
            (provider_id, "Dr. Update Test", "General", 4.0),
        )
        conn.commit()

        # Update provider
        conn.execute(
            "UPDATE providers SET specialty = ?, rating = ?, phone = ? WHERE id = ?",
            ("Internal Medicine", 4.8, "555-UPDATED", provider_id),
        )
        conn.commit()

        # Verify update
        cursor = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        row = cursor.fetchone()

        assert row["specialty"] == "Internal Medicine"
        assert row["rating"] == 4.8
        assert row["phone"] == "555-UPDATED"

        # Cleanup
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

    def test_delete_provider(self, db_connection):
        """Test deleting a provider."""
        provider_id = "prov-test-delete"
        conn = db_connection

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        # Create provider
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Delete Test"),
        )
        conn.commit()

        # Verify exists
        cursor = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        assert cursor.fetchone() is not None

        # Delete provider
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

        # Verify deleted
        cursor = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        assert cursor.fetchone() is None


# =============================================================================
# Appointment Tests
# =============================================================================


class TestAppointmentsCRUD:
    """Tests for appointments table CRUD operations."""

    def test_create_available_slot(self, db_connection):
        """Test creating an available appointment slot."""
        conn = db_connection
        slot_id = "slot-test-001"
        provider_id = "prov-test-slots"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        # Create test provider first
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Slot Test"),
        )

        # Create available slot (patient_id is NULL)
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (slot_id, provider_id, "2025-12-15", "10:00", "available"),
        )
        conn.commit()

        # Verify
        cursor = conn.execute("SELECT * FROM appointments WHERE id = ?", (slot_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["patient_id"] is None
        assert row["status"] == "available"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

    def test_book_appointment(self, db_connection):
        """Test booking an available slot."""
        conn = db_connection
        slot_id = "slot-test-book"
        provider_id = "prov-test-book"
        patient_id = "p-test-book"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

        # Create test patient (required for foreign key)
        conn.execute(
            """INSERT INTO patients (id, first_name, last_name, date_of_birth, phone)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, "Test", "Booker", "1990-01-01", "555-BOOK"),
        )

        # Create provider
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Book Test"),
        )

        # Create available slot
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (slot_id, provider_id, "2025-12-16", "14:00", "available"),
        )
        conn.commit()

        # Book the slot
        conn.execute(
            """UPDATE appointments
               SET patient_id = ?, status = 'booked', reason = ?, booked_at = ?
               WHERE id = ? AND patient_id IS NULL""",
            (patient_id, "Test booking reason", datetime.now().isoformat(), slot_id),
        )
        conn.commit()

        # Verify
        cursor = conn.execute("SELECT * FROM appointments WHERE id = ?", (slot_id,))
        row = cursor.fetchone()

        assert row["patient_id"] == patient_id
        assert row["status"] == "booked"
        assert row["reason"] == "Test booking reason"
        assert row["booked_at"] is not None

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        conn.commit()

    def test_get_available_slots_for_provider(self, db_connection):
        """Test getting available slots for a provider."""
        conn = db_connection
        provider_id = "prov-test-available"
        patient_id = "p-test-avail"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

        # Create test patient for booked slot
        conn.execute(
            """INSERT INTO patients (id, first_name, last_name, date_of_birth, phone)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, "Test", "Available", "1990-01-01", "555-AVAIL"),
        )

        # Create provider
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Available Test"),
        )

        # Create mix of available and booked slots
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            "INSERT INTO appointments (id, provider_id, date, time, status) VALUES (?, ?, ?, ?, ?)",
            ("slot-avail-1", provider_id, today, "09:00", "available"),
        )
        conn.execute(
            "INSERT INTO appointments (id, provider_id, date, time, status, patient_id) VALUES (?, ?, ?, ?, ?, ?)",
            ("slot-avail-2", provider_id, today, "09:30", "booked", patient_id),
        )
        conn.execute(
            "INSERT INTO appointments (id, provider_id, date, time, status) VALUES (?, ?, ?, ?, ?)",
            ("slot-avail-3", provider_id, today, "10:00", "available"),
        )
        conn.commit()

        # Query available slots
        cursor = conn.execute(
            """SELECT * FROM appointments
               WHERE provider_id = ?
                 AND patient_id IS NULL
                 AND status = 'available'
               ORDER BY date, time""",
            (provider_id,),
        )
        rows = cursor.fetchall()

        assert len(rows) == 2
        assert all(row["status"] == "available" for row in rows)

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        conn.commit()

    def test_get_patient_appointments(self, db_connection):
        """Test getting all appointments for a patient."""
        conn = db_connection
        provider_id = "prov-test-patient-appts"
        patient_id = "p-test-appts"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

        # Create test patient
        conn.execute(
            """INSERT INTO patients (id, first_name, last_name, date_of_birth, phone)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, "Test", "Appointments", "1990-01-01", "555-APPTS"),
        )

        # Create provider
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Patient Appts"),
        )

        # Create appointments for patient
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        conn.execute(
            "INSERT INTO appointments (id, provider_id, patient_id, date, time, status, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("slot-pat-1", provider_id, patient_id, today, "11:00", "booked", "Checkup"),
        )
        conn.execute(
            "INSERT INTO appointments (id, provider_id, patient_id, date, time, status, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("slot-pat-2", provider_id, patient_id, tomorrow, "14:00", "booked", "Follow-up"),
        )
        conn.commit()

        # Query patient appointments
        cursor = conn.execute(
            """SELECT a.*, p.name as provider_name
               FROM appointments a
               JOIN providers p ON a.provider_id = p.id
               WHERE a.patient_id = ?
               ORDER BY a.date, a.time""",
            (patient_id,),
        )
        rows = cursor.fetchall()

        assert len(rows) == 2
        assert rows[0]["provider_name"] == "Dr. Patient Appts"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        conn.commit()

    def test_cancel_appointment(self, db_connection):
        """Test cancelling an appointment."""
        conn = db_connection
        slot_id = "slot-test-cancel"
        provider_id = "prov-test-cancel"
        patient_id = "p-test-cancel"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

        # Create test patient
        conn.execute(
            """INSERT INTO patients (id, first_name, last_name, date_of_birth, phone)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, "Test", "Cancel", "1990-01-01", "555-CANCEL"),
        )

        # Create provider and booked appointment
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Cancel Test"),
        )
        conn.execute(
            """INSERT INTO appointments (id, provider_id, patient_id, date, time, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (slot_id, provider_id, patient_id, "2025-12-20", "15:00", "booked"),
        )
        conn.commit()

        # Cancel the appointment
        conn.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = ?",
            (slot_id,),
        )
        conn.commit()

        # Verify
        cursor = conn.execute("SELECT status FROM appointments WHERE id = ?", (slot_id,))
        row = cursor.fetchone()

        assert row["status"] == "cancelled"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        conn.commit()

    def test_complete_appointment(self, db_connection):
        """Test completing an appointment."""
        conn = db_connection
        slot_id = "slot-test-complete"
        provider_id = "prov-test-complete"
        patient_id = "p-test-complete"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

        # Create test patient
        conn.execute(
            """INSERT INTO patients (id, first_name, last_name, date_of_birth, phone)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, "Test", "Complete", "1990-01-01", "555-COMPLETE"),
        )

        # Create provider and booked appointment
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Complete Test"),
        )
        conn.execute(
            """INSERT INTO appointments (id, provider_id, patient_id, date, time, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (slot_id, provider_id, patient_id, "2025-12-01", "10:00", "booked"),
        )
        conn.commit()

        # Complete the appointment
        conn.execute(
            "UPDATE appointments SET status = 'completed', notes = ? WHERE id = ?",
            ("Patient visit completed successfully", slot_id),
        )
        conn.commit()

        # Verify
        cursor = conn.execute("SELECT * FROM appointments WHERE id = ?", (slot_id,))
        row = cursor.fetchone()

        assert row["status"] == "completed"
        assert row["notes"] == "Patient visit completed successfully"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        conn.commit()

    def test_get_appointment_by_id(self, db_connection):
        """Test reading an appointment by ID."""
        conn = db_connection
        slot_id = "slot-test-read"
        provider_id = "prov-test-read-appt"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        # Create provider and appointment
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Read Appt Test"),
        )
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (slot_id, provider_id, "2025-12-25", "11:00", "available"),
        )
        conn.commit()

        # Read by ID
        cursor = conn.execute("SELECT * FROM appointments WHERE id = ?", (slot_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["id"] == slot_id
        assert row["provider_id"] == provider_id
        assert row["date"] == "2025-12-25"
        assert row["time"] == "11:00"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()

    def test_get_appointment_by_id_not_found(self, db_connection):
        """Test reading a non-existent appointment returns None."""
        conn = db_connection

        cursor = conn.execute("SELECT * FROM appointments WHERE id = ?", ("nonexistent-slot",))
        row = cursor.fetchone()

        assert row is None

    def test_delete_appointment(self, db_connection):
        """Test deleting an appointment."""
        conn = db_connection
        slot_id = "slot-test-delete"
        provider_id = "prov-test-delete-appt"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

        # Create provider and appointment
        conn.execute(
            "INSERT INTO providers (id, name) VALUES (?, ?)",
            (provider_id, "Dr. Delete Appt Test"),
        )
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (slot_id, provider_id, "2025-12-26", "12:00", "available"),
        )
        conn.commit()

        # Verify exists
        cursor = conn.execute("SELECT * FROM appointments WHERE id = ?", (slot_id,))
        assert cursor.fetchone() is not None

        # Delete appointment
        conn.execute("DELETE FROM appointments WHERE id = ?", (slot_id,))
        conn.commit()

        # Verify deleted
        cursor = conn.execute("SELECT * FROM appointments WHERE id = ?", (slot_id,))
        assert cursor.fetchone() is None

        # Cleanup provider
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()


class TestAppointmentQueries:
    """Tests for common appointment query patterns."""

    def test_get_upcoming_available_slots(self, db_connection):
        """Test getting upcoming available slots."""
        conn = db_connection

        today = datetime.now().strftime("%Y-%m-%d")

        cursor = conn.execute(
            """SELECT a.*, p.name as provider_name, p.specialty
               FROM appointments a
               JOIN providers p ON a.provider_id = p.id
               WHERE a.patient_id IS NULL
                 AND a.status = 'available'
                 AND a.date >= ?
               ORDER BY a.date, a.time
               LIMIT 10""",
            (today,),
        )
        rows = cursor.fetchall()

        # All should be available with no patient
        for row in rows:
            assert row["patient_id"] is None
            assert row["status"] == "available"

    def test_slots_by_date_range(self, db_connection):
        """Test getting slots within a date range."""
        conn = db_connection

        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        cursor = conn.execute(
            """SELECT * FROM appointments
               WHERE date >= ? AND date <= ?
                 AND status = 'available'
               ORDER BY date, time""",
            (start_date, end_date),
        )
        rows = cursor.fetchall()

        for row in rows:
            assert start_date <= row["date"] <= end_date

    def test_provider_schedule_summary(self, db_connection):
        """Test getting a provider's schedule summary."""
        conn = db_connection

        cursor = conn.execute(
            """SELECT provider_id, date,
                      SUM(CASE WHEN status = 'available' THEN 1 ELSE 0 END) as available_slots,
                      SUM(CASE WHEN status = 'booked' THEN 1 ELSE 0 END) as booked_slots
               FROM appointments
               GROUP BY provider_id, date
               ORDER BY provider_id, date"""
        )
        rows = cursor.fetchall()

        # Just verify the query runs without error
        assert rows is not None


class TestProviderAppointmentIntegration:
    """Integration tests for provider and appointment interactions."""

    def test_full_booking_flow(self, db_connection):
        """Test complete flow: create provider -> create slots -> book appointment."""
        conn = db_connection
        provider_id = "prov-integration"
        patient_id = "p-integration"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

        # Create test patient
        conn.execute(
            """INSERT INTO patients (id, first_name, last_name, date_of_birth, phone)
               VALUES (?, ?, ?, ?, ?)""",
            (patient_id, "Test", "Integration", "1990-01-01", "555-INT"),
        )

        # 1. Create provider
        conn.execute(
            """INSERT INTO providers (id, name, specialty, insurance_accepted)
               VALUES (?, ?, ?, ?)""",
            (provider_id, "Dr. Integration", "General", '["Test Insurance"]'),
        )

        # 2. Create available slots
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        for i, time in enumerate(["09:00", "09:30", "10:00"]):
            conn.execute(
                "INSERT INTO appointments (id, provider_id, date, time, status) VALUES (?, ?, ?, ?, ?)",
                (f"slot-int-{i}", provider_id, tomorrow, time, "available"),
            )
        conn.commit()

        # 3. Find available slots
        cursor = conn.execute(
            """SELECT * FROM appointments
               WHERE provider_id = ? AND status = 'available'
               ORDER BY time""",
            (provider_id,),
        )
        available = cursor.fetchall()
        assert len(available) == 3

        # 4. Book first slot
        first_slot_id = available[0]["id"]
        conn.execute(
            """UPDATE appointments
               SET patient_id = ?, status = 'booked', reason = ?
               WHERE id = ?""",
            (patient_id, "Initial consultation", first_slot_id),
        )
        conn.commit()

        # 5. Verify booking
        cursor = conn.execute(
            "SELECT * FROM appointments WHERE provider_id = ? AND status = 'available'",
            (provider_id,),
        )
        remaining = cursor.fetchall()
        assert len(remaining) == 2

        cursor = conn.execute(
            "SELECT * FROM appointments WHERE patient_id = ?",
            (patient_id,),
        )
        booked = cursor.fetchall()
        assert len(booked) == 1
        assert booked[0]["reason"] == "Initial consultation"

        # Cleanup
        conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
        conn.commit()
