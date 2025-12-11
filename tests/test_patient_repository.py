"""Tests for patient repository functionality."""

import pytest
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "assort_intake_bot"))

from patient_intake.database import init_database, PatientRepository
from patient_intake.database.patient_repository import Patient
from patient_intake.database.connection import get_connection


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Initialize database before tests."""
    init_database()
    yield


@pytest.fixture
def repo():
    """Get a repository instance."""
    return PatientRepository()


@pytest.fixture
def test_patient(repo):
    """Create a test patient for tests that need one."""
    patient = Patient(
        id="p-test-fixture",
        first_name="Test",
        last_name="Fixture",
        date_of_birth="1990-01-01",
        phone="555-FIXTURE",
        email="test.fixture@email.com",
    )

    # Clean up if exists
    conn = get_connection()
    conn.execute("DELETE FROM visits WHERE patient_id = ?", (patient.id,))
    conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient.id,))
    conn.execute("DELETE FROM patients WHERE id = ?", (patient.id,))
    conn.commit()
    conn.close()

    created = repo.create(patient, changed_by="test")
    yield created

    # Cleanup after test
    conn = get_connection()
    conn.execute("DELETE FROM visits WHERE patient_id = ?", (patient.id,))
    conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient.id,))
    conn.execute("DELETE FROM patients WHERE id = ?", (patient.id,))
    conn.commit()
    conn.close()


class TestFindExistingPatient:
    """Tests for find_existing_patient method."""

    def test_find_by_phone(self, repo, test_patient):
        patient = repo.find_existing_patient(phone="555-FIXTURE")
        assert patient is not None
        assert patient.first_name == "Test"

    def test_find_by_email(self, repo, test_patient):
        patient = repo.find_existing_patient(email="test.fixture@email.com")
        assert patient is not None
        assert patient.last_name == "Fixture"

    def test_find_by_name_and_dob(self, repo, test_patient):
        patient = repo.find_existing_patient(
            first_name="Test",
            last_name="Fixture",
            date_of_birth="1990-01-01"
        )
        assert patient is not None
        assert patient.phone == "555-FIXTURE"

    def test_not_found_returns_none(self, repo):
        patient = repo.find_existing_patient(phone="999-NONEXISTENT")
        assert patient is None


class TestPatientCRUD:
    """Tests for patient CRUD operations."""

    def test_create_patient(self, repo):
        patient = Patient(
            id="p-test-create",
            first_name="Create",
            last_name="Test",
            date_of_birth="1985-05-15",
            phone="555-CREATE",
        )

        # Cleanup first
        conn = get_connection()
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient.id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient.id,))
        conn.commit()
        conn.close()

        created = repo.create(patient, changed_by="test")

        assert created.id == "p-test-create"
        assert created.created_at is not None

        # Cleanup
        conn = get_connection()
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient.id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient.id,))
        conn.commit()
        conn.close()

    def test_get_by_id(self, repo, test_patient):
        patient = repo.get_by_id(test_patient.id)
        assert patient is not None
        assert patient.first_name == "Test"

    def test_get_by_id_not_found(self, repo):
        patient = repo.get_by_id("nonexistent-id")
        assert patient is None

    def test_update_patient(self, repo, test_patient):
        updated = repo.update(
            test_patient.id,
            {"phone": "555-UPDATED", "city": "Test City"},
            changed_by="test"
        )

        assert updated is not None
        assert updated.phone == "555-UPDATED"
        assert updated.city == "Test City"

    def test_delete_patient(self, repo):
        """Test deleting a patient."""
        patient = Patient(
            id="p-test-delete",
            first_name="Delete",
            last_name="Test",
            date_of_birth="1985-05-15",
            phone="555-DELETE",
        )

        # Cleanup first
        conn = get_connection()
        conn.execute("DELETE FROM visits WHERE patient_id = ?", (patient.id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient.id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient.id,))
        conn.commit()
        conn.close()

        # Create patient
        repo.create(patient, changed_by="test")

        # Verify exists
        assert repo.get_by_id(patient.id) is not None

        # Delete patient (need to delete related records first due to FK)
        conn = get_connection()
        conn.execute("DELETE FROM visits WHERE patient_id = ?", (patient.id,))
        conn.execute("DELETE FROM patient_change_log WHERE patient_id = ?", (patient.id,))
        conn.execute("DELETE FROM patients WHERE id = ?", (patient.id,))
        conn.commit()
        conn.close()

        # Verify deleted
        assert repo.get_by_id(patient.id) is None


class TestAuditLogging:
    """Tests for audit logging functionality."""

    def test_create_logs_changes(self, repo, test_patient):
        history = repo.get_change_history(test_patient.id)

        # Should have CREATE entries for each non-null field
        create_entries = [h for h in history if h["change_type"] == "CREATE"]
        assert len(create_entries) > 0

    def test_update_logs_changes(self, repo, test_patient):
        # Make an update
        repo.update(test_patient.id, {"city": "Audit Test City"}, changed_by="test")

        history = repo.get_change_history(test_patient.id)
        update_entries = [h for h in history if h["change_type"] == "UPDATE"]

        assert len(update_entries) > 0
        city_update = next((h for h in update_entries if h["field_name"] == "city"), None)
        assert city_update is not None
        assert city_update["new_value"] == "Audit Test City"


class TestCheckWhatChanged:
    """Tests for change detection."""

    def test_detects_changes(self, repo, test_patient):
        new_data = {
            "phone": "555-CHANGED",
            "email": test_patient.email,  # Unchanged
            "city": "New City",
        }

        changes = repo.check_what_changed(test_patient, new_data)

        assert "phone" in changes
        assert "city" in changes
        assert "email" not in changes

    def test_no_changes(self, repo, test_patient):
        same_data = {
            "phone": test_patient.phone,
            "email": test_patient.email,
        }

        changes = repo.check_what_changed(test_patient, same_data)
        assert len(changes) == 0


class TestPatientSummary:
    """Tests for patient summary."""

    def test_get_summary(self, repo, test_patient):
        summary = repo.get_patient_summary(test_patient.id)

        assert summary is not None
        assert summary["first_name"] == "Test"
        assert summary["name"] == "Test Fixture"
        assert "recent_complaints" in summary

    def test_summary_not_found(self, repo):
        summary = repo.get_patient_summary("nonexistent-id")
        assert summary is None


class TestVisits:
    """Tests for visit operations."""

    def test_create_visit(self, repo, test_patient):
        visit = repo.create_visit(
            patient_id=test_patient.id,
            chief_complaint="Test complaint",
            symptoms='["symptom1", "symptom2"]',
            severity=5
        )

        assert visit.id is not None
        assert visit.chief_complaint == "Test complaint"
        assert visit.status == "pending"

    def test_get_visit_history(self, repo, test_patient):
        # Create a visit first
        repo.create_visit(test_patient.id, "History test")

        visits = repo.get_visit_history(test_patient.id)
        assert len(visits) > 0

    def test_get_recent_complaints(self, repo, test_patient):
        repo.create_visit(test_patient.id, "Complaint 1")
        repo.create_visit(test_patient.id, "Complaint 2")

        complaints = repo.get_recent_complaints(test_patient.id, limit=2)
        assert len(complaints) <= 2

    def test_update_visit_status(self, repo, test_patient):
        visit = repo.create_visit(test_patient.id, "Status test")

        updated = repo.update_visit_status(visit.id, "completed")

        assert updated.status == "completed"
        assert updated.completed_at is not None

    def test_delete_visit(self, repo, test_patient):
        """Test deleting a visit."""
        # Create a visit
        visit = repo.create_visit(test_patient.id, "Delete test visit")
        visit_id = visit.id

        # Verify exists
        visits = repo.get_visit_history(test_patient.id)
        assert any(v.id == visit_id for v in visits)

        # Delete visit
        conn = get_connection()
        conn.execute("DELETE FROM visits WHERE id = ?", (visit_id,))
        conn.commit()
        conn.close()

        # Verify deleted
        visits = repo.get_visit_history(test_patient.id)
        assert not any(v.id == visit_id for v in visits)
