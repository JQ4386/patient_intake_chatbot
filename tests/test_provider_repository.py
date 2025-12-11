"""Tests for the ProviderRepository class."""

import json
import pytest
from datetime import datetime, timedelta

from assort_intake_bot.patient_intake.database import init_database
from assort_intake_bot.patient_intake.database.connection import get_connection
from assort_intake_bot.patient_intake.database.provider_repository import (
    ProviderRepository,
    Provider,
    Appointment,
)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Initialize database before tests."""
    init_database()
    yield


@pytest.fixture
def repo():
    """Get a fresh ProviderRepository instance."""
    return ProviderRepository()


@pytest.fixture
def db_connection():
    """Get a database connection - for backwards compatibility."""
    conn = get_connection()
    yield conn
    conn.close()


@pytest.fixture
def test_provider(request):
    """Create a test provider and clean up after."""
    # Use unique ID based on test name to avoid conflicts
    test_name = request.node.name
    provider_id = f"prov-test-{test_name[:20]}"
    conn = get_connection()
    conn.execute("PRAGMA busy_timeout = 5000")

    # Cleanup first
    conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
    conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

    # Insert test provider
    conn.execute(
        """INSERT INTO providers
           (id, name, specialty, insurance_accepted, conditions_treated, rating, accepting_new_patients)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            provider_id,
            "Dr. Test Repository",
            "Family Medicine",
            '["Blue Cross PPO", "Aetna HMO", "Kaiser"]',
            '["back pain", "headache", "cold/flu"]',
            4.5,
            1,
        ),
    )
    conn.commit()
    conn.close()

    yield provider_id

    # Cleanup
    conn = get_connection()
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
    conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    conn.commit()
    conn.close()


@pytest.fixture
def test_patient(request):
    """Create a test patient for appointment booking."""
    # Use unique ID based on test name to avoid conflicts
    test_name = request.node.name
    patient_id = f"p-test-{test_name[:20]}"
    conn = get_connection()
    conn.execute("PRAGMA busy_timeout = 5000")

    # Cleanup
    conn.execute("DELETE FROM appointments WHERE patient_id = ?", (patient_id,))
    conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
    conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))

    # Create patient
    conn.execute(
        """INSERT INTO patients (id, first_name, last_name, date_of_birth, phone)
           VALUES (?, ?, ?, ?, ?)""",
        (patient_id, "Test", "Booker", "1990-01-01", "555-BOOK"),
    )
    conn.commit()
    conn.close()

    yield patient_id

    # Cleanup
    conn = get_connection()
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("DELETE FROM appointments WHERE patient_id = ?", (patient_id,))
    conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient_id,))
    conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()


class TestProviderRepositoryFindProviders:
    """Tests for find_providers method."""

    def test_find_all_providers(self, repo, test_provider):
        """Test finding providers without filters."""
        providers = repo.find_providers(limit=10)
        assert len(providers) > 0
        assert all(isinstance(p, Provider) for p in providers)

    def test_find_providers_by_insurance(self, repo, test_provider):
        """Test finding providers by insurance."""
        providers = repo.find_providers(insurance="Blue Cross")
        assert len(providers) > 0
        for p in providers:
            assert p.insurance_accepted is not None
            # Check that Blue Cross is in the list
            assert any("Blue Cross" in ins for ins in p.insurance_accepted)

    def test_find_providers_by_condition(self, repo, test_provider):
        """Test finding providers by condition."""
        providers = repo.find_providers(condition="back pain")
        assert len(providers) > 0
        for p in providers:
            assert p.conditions_treated is not None
            assert any("back pain" in cond for cond in p.conditions_treated)

    def test_find_providers_by_specialty(self, repo, test_provider):
        """Test finding providers by specialty."""
        providers = repo.find_providers(specialty="Family Medicine")
        assert len(providers) > 0
        for p in providers:
            assert "Family Medicine" in p.specialty

    def test_find_providers_combined_filters(self, repo, test_provider):
        """Test finding providers with multiple filters."""
        providers = repo.find_providers(
            insurance="Blue Cross",
            condition="back pain",
            limit=5,
        )
        # May or may not find results depending on data
        for p in providers:
            assert p.insurance_accepted is not None
            assert p.conditions_treated is not None

    def test_find_providers_no_results(self, repo):
        """Test finding providers with no matching results."""
        providers = repo.find_providers(insurance="NonexistentInsurance12345")
        assert providers == []

    def test_find_providers_ordered_by_rating(self, repo, test_provider):
        """Test that providers are ordered by rating descending."""
        providers = repo.find_providers(limit=10)
        if len(providers) > 1:
            for i in range(len(providers) - 1):
                assert providers[i].rating >= providers[i + 1].rating

    def test_find_providers_limit(self, repo, test_provider):
        """Test that limit parameter works."""
        providers = repo.find_providers(limit=2)
        assert len(providers) <= 2


class TestProviderRepositoryGetById:
    """Tests for get_by_id method."""

    def test_get_provider_by_id(self, repo, test_provider):
        """Test getting a provider by ID."""
        provider = repo.get_by_id(test_provider)
        assert provider is not None
        assert provider.id == test_provider
        assert provider.name == "Dr. Test Repository"
        assert provider.specialty == "Family Medicine"

    def test_get_provider_by_id_not_found(self, repo):
        """Test getting a non-existent provider."""
        provider = repo.get_by_id("nonexistent-provider-id")
        assert provider is None

    def test_provider_json_fields_parsed(self, repo, test_provider):
        """Test that JSON fields are properly parsed."""
        provider = repo.get_by_id(test_provider)
        assert provider is not None
        assert isinstance(provider.insurance_accepted, list)
        assert isinstance(provider.conditions_treated, list)
        assert "Blue Cross PPO" in provider.insurance_accepted
        assert "back pain" in provider.conditions_treated


class TestProviderRepositoryGetAvailableSlots:
    """Tests for get_available_slots method."""

    def test_get_available_slots(self, repo, test_provider):
        """Test getting available slots for a provider."""
        conn = get_connection()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Create some test slots
        for i, time in enumerate(["09:00", "09:30", "10:00"]):
            conn.execute(
                """INSERT INTO appointments (id, provider_id, date, time, status)
                   VALUES (?, ?, ?, ?, ?)""",
                (f"slot-test-{i}", test_provider, tomorrow, time, "available"),
            )
        conn.commit()
        conn.close()

        slots = repo.get_available_slots(test_provider)
        assert len(slots) >= 3
        assert all(isinstance(s, Appointment) for s in slots)
        assert all(s.status == "available" for s in slots)

    def test_get_available_slots_excludes_booked(self, repo, test_provider, test_patient):
        """Test that booked slots are not returned."""
        conn = get_connection()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Create available and booked slots
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            ("slot-available-test", test_provider, tomorrow, "11:00", "available"),
        )
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status, patient_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("slot-booked-test", test_provider, tomorrow, "11:30", "booked", test_patient),
        )
        conn.commit()
        conn.close()

        slots = repo.get_available_slots(test_provider)
        slot_ids = [s.id for s in slots]
        assert "slot-available-test" in slot_ids
        assert "slot-booked-test" not in slot_ids

    def test_get_available_slots_from_date(self, repo, test_provider):
        """Test getting slots from a specific date."""
        conn = get_connection()
        future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            ("slot-future-test", test_provider, future_date, "14:00", "available"),
        )
        conn.commit()
        conn.close()

        slots = repo.get_available_slots(test_provider, from_date=future_date)
        assert any(s.date == future_date for s in slots)

    def test_get_available_slots_limit(self, repo, test_provider):
        """Test that limit parameter works."""
        slots = repo.get_available_slots(test_provider, limit=2)
        assert len(slots) <= 2

    def test_get_available_slots_ordered_by_datetime(self, repo, test_provider):
        """Test that slots are ordered by date and time."""
        slots = repo.get_available_slots(test_provider, limit=10)
        if len(slots) > 1:
            for i in range(len(slots) - 1):
                current = (slots[i].date, slots[i].time)
                next_slot = (slots[i + 1].date, slots[i + 1].time)
                assert current <= next_slot


class TestProviderRepositoryBookAppointment:
    """Tests for book_appointment method."""

    def test_book_appointment_success(self, repo, test_provider, test_patient):
        """Test successfully booking an appointment."""
        conn = get_connection()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Create available slot
        slot_id = "slot-book-success"
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (slot_id, test_provider, tomorrow, "15:00", "available"),
        )
        conn.commit()
        conn.close()

        # Book the appointment
        appointment = repo.book_appointment(
            appointment_id=slot_id,
            patient_id=test_patient,
            reason="Test booking reason",
        )

        assert appointment is not None
        assert appointment.patient_id == test_patient
        assert appointment.status == "booked"
        assert appointment.reason == "Test booking reason"
        assert appointment.booked_at is not None

    def test_book_appointment_already_booked(self, repo, test_provider, test_patient):
        """Test booking an already booked slot fails."""
        conn = get_connection()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Create already booked slot (use test_patient as the booker)
        slot_id = "slot-already-booked"
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status, patient_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (slot_id, test_provider, tomorrow, "15:30", "booked", test_patient),
        )
        conn.commit()
        conn.close()

        # Try to book again with a different hypothetical patient
        # Since slot is already booked, this should fail regardless
        appointment = repo.book_appointment(
            appointment_id=slot_id,
            patient_id=test_patient,
        )

        assert appointment is None

    def test_book_appointment_with_reason(self, repo, test_provider, test_patient):
        """Test booking an appointment with a reason."""
        conn = get_connection()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        slot_id = "slot-with-reason"
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (slot_id, test_provider, tomorrow, "16:00", "available"),
        )
        conn.commit()
        conn.close()

        appointment = repo.book_appointment(
            appointment_id=slot_id,
            patient_id=test_patient,
            reason="Follow-up visit",
        )

        assert appointment is not None
        assert appointment.reason == "Follow-up visit"

    def test_book_nonexistent_appointment(self, repo, test_patient):
        """Test booking a non-existent appointment slot."""
        appointment = repo.book_appointment(
            appointment_id="nonexistent-slot-id",
            patient_id=test_patient,
        )
        assert appointment is None


class TestProviderRepositoryGetAppointmentById:
    """Tests for get_appointment_by_id method."""

    def test_get_appointment_by_id(self, repo, test_provider):
        """Test getting an appointment by ID."""
        conn = get_connection()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        slot_id = "slot-get-by-id"
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (slot_id, test_provider, tomorrow, "17:00", "available"),
        )
        conn.commit()
        conn.close()

        appointment = repo.get_appointment_by_id(slot_id)
        assert appointment is not None
        assert appointment.id == slot_id
        assert appointment.provider_id == test_provider
        assert appointment.date == tomorrow
        assert appointment.time == "17:00"

    def test_get_appointment_by_id_not_found(self, repo):
        """Test getting a non-existent appointment."""
        appointment = repo.get_appointment_by_id("nonexistent-slot")
        assert appointment is None
