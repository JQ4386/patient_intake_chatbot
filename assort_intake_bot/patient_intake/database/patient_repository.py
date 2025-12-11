"""Patient repository with CRUD operations and audit logging."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from .connection import get_connection


@dataclass
class Patient:
    id: str
    first_name: str
    last_name: str
    date_of_birth: str
    phone: str
    email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    address_validated: bool = False
    insurance_payer: str | None = None
    insurance_plan: str | None = None
    insurance_member_id: str | None = None
    insurance_group_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class Visit:
    id: str
    patient_id: str
    chief_complaint: str
    symptoms: str | None = None
    symptom_duration: str | None = None
    severity: int | None = None
    status: str = "pending"
    created_at: str | None = None
    completed_at: str | None = None


class PatientRepository:
    """Repository for patient CRUD operations with audit logging."""

    # Fields that can be updated
    PATIENT_FIELDS = [
        "first_name", "last_name", "date_of_birth", "phone", "email",
        "address_line1", "address_line2", "city", "state", "zip_code",
        "address_validated", "insurance_payer", "insurance_plan",
        "insurance_member_id", "insurance_group_id"
    ]

    def find_existing_patient(
        self,
        phone: str | None = None,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        date_of_birth: str | None = None
    ) -> Patient | None:
        """Find existing patient by phone, email, or name+DOB."""
        conn = get_connection()
        cursor = conn.cursor()

        # Try phone first
        if phone:
            cursor.execute("SELECT * FROM patients WHERE phone = ?", (phone,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return self._row_to_patient(row)

        # Try email
        if email:
            cursor.execute("SELECT * FROM patients WHERE email = ?", (email,))
            row = cursor.fetchone()
            if row:
                conn.close()
                return self._row_to_patient(row)

        # Try name + DOB
        if first_name and last_name and date_of_birth:
            cursor.execute(
                "SELECT * FROM patients WHERE first_name = ? AND last_name = ? AND date_of_birth = ?",
                (first_name, last_name, date_of_birth)
            )
            row = cursor.fetchone()
            if row:
                conn.close()
                return self._row_to_patient(row)

        conn.close()
        return None

    def find_patients_by_name(
        self,
        first_name: str,
        last_name: str,
    ) -> list[Patient]:
        """Find patients matching first and last name (for DOB verification)."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM patients WHERE LOWER(first_name) = LOWER(?) AND LOWER(last_name) = LOWER(?)",
            (first_name, last_name)
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_patient(row) for row in rows]

    def create(self, patient: Patient, changed_by: str = "system") -> Patient:
        """Create a new patient with audit logging."""
        conn = get_connection()
        cursor = conn.cursor()

        patient.id = patient.id or str(uuid.uuid4())
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO patients (
                id, first_name, last_name, date_of_birth, phone, email,
                address_line1, address_line2, city, state, zip_code, address_validated,
                insurance_payer, insurance_plan, insurance_member_id, insurance_group_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            patient.id, patient.first_name, patient.last_name, patient.date_of_birth,
            patient.phone, patient.email, patient.address_line1, patient.address_line2,
            patient.city, patient.state, patient.zip_code, int(patient.address_validated),
            patient.insurance_payer, patient.insurance_plan, patient.insurance_member_id,
            patient.insurance_group_id, now, now
        ))

        # Log creation for each non-null field
        for field in self.PATIENT_FIELDS:
            value = getattr(patient, field)
            if value is not None:
                self._log_change(cursor, patient.id, field, None, str(value), "CREATE", changed_by)

        conn.commit()
        conn.close()

        patient.created_at = now
        patient.updated_at = now
        return patient

    def get_by_id(self, patient_id: str) -> Patient | None:
        """Get a patient by ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_patient(row) if row else None

    def update(self, patient_id: str, updates: dict, changed_by: str = "system") -> Patient | None:
        """Update patient fields with audit logging."""
        conn = get_connection()
        cursor = conn.cursor()

        # Get current patient
        cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        current = dict(row)
        now = datetime.now().isoformat()

        # Filter valid fields and detect changes
        valid_updates = {}
        for field, new_value in updates.items():
            if field in self.PATIENT_FIELDS:
                old_value = current.get(field)
                # Convert address_validated for comparison
                if field == "address_validated":
                    old_value = bool(old_value)
                    new_value = bool(new_value)

                if old_value != new_value:
                    valid_updates[field] = new_value
                    self._log_change(
                        cursor, patient_id, field,
                        str(old_value) if old_value is not None else None,
                        str(new_value) if new_value is not None else None,
                        "UPDATE", changed_by
                    )

        if valid_updates:
            # Build update query
            set_clause = ", ".join(f"{field} = ?" for field in valid_updates)
            set_clause += ", updated_at = ?"
            values = list(valid_updates.values()) + [now, patient_id]

            cursor.execute(
                f"UPDATE patients SET {set_clause} WHERE id = ?",
                values
            )

        conn.commit()
        conn.close()
        return self.get_by_id(patient_id)

    def check_what_changed(self, patient: Patient, new_data: dict) -> dict:
        """Compare current patient data with new data, return differences."""
        changes = {}
        for field, new_value in new_data.items():
            if field in self.PATIENT_FIELDS:
                current_value = getattr(patient, field, None)
                if current_value != new_value:
                    changes[field] = {"old": current_value, "new": new_value}
        return changes

    def get_patient_summary(self, patient_id: str) -> dict | None:
        """Get a quick summary of patient for chatbot use."""
        patient = self.get_by_id(patient_id)
        if not patient:
            return None

        visits = self.get_visit_history(patient_id, limit=3)
        recent_complaints = [v.chief_complaint for v in visits]

        return {
            "id": patient.id,
            "name": f"{patient.first_name} {patient.last_name}",
            "first_name": patient.first_name,
            "phone": patient.phone,
            "has_insurance": bool(patient.insurance_payer),
            "insurance_payer": patient.insurance_payer,
            "recent_complaints": recent_complaints,
            "visit_count": len(self.get_visit_history(patient_id)),
        }

    def get_change_history(self, patient_id: str, limit: int = 50) -> list[dict]:
        """Get audit trail for a patient."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM patient_change_log
            WHERE patient_id = ?
            ORDER BY changed_at DESC
            LIMIT ?
        """, (patient_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # Visit methods

    def create_visit(
        self,
        patient_id: str,
        chief_complaint: str,
        symptoms: str | None = None,
        symptom_duration: str | None = None,
        severity: int | None = None
    ) -> Visit:
        """Create a new visit record."""
        conn = get_connection()
        cursor = conn.cursor()

        visit_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO visits (id, patient_id, chief_complaint, symptoms, symptom_duration, severity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (visit_id, patient_id, chief_complaint, symptoms, symptom_duration, severity, now))

        conn.commit()
        conn.close()

        return Visit(
            id=visit_id,
            patient_id=patient_id,
            chief_complaint=chief_complaint,
            symptoms=symptoms,
            symptom_duration=symptom_duration,
            severity=severity,
            created_at=now
        )

    def get_visit_history(self, patient_id: str, limit: int | None = None) -> list[Visit]:
        """Get visit history for a patient."""
        conn = get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM visits WHERE patient_id = ? ORDER BY created_at DESC"
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, (patient_id,))
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_visit(row) for row in rows]

    def get_recent_complaints(self, patient_id: str, limit: int = 5) -> list[str]:
        """Get recent chief complaints for a patient."""
        visits = self.get_visit_history(patient_id, limit=limit)
        return [v.chief_complaint for v in visits]

    def update_visit_status(self, visit_id: str, status: str) -> Visit | None:
        """Update visit status."""
        conn = get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        completed_at = now if status == "completed" else None

        cursor.execute("""
            UPDATE visits SET status = ?, completed_at = ? WHERE id = ?
        """, (status, completed_at, visit_id))

        conn.commit()

        cursor.execute("SELECT * FROM visits WHERE id = ?", (visit_id,))
        row = cursor.fetchone()
        conn.close()

        return self._row_to_visit(row) if row else None

    # Private helpers

    def _log_change(
        self,
        cursor,
        patient_id: str,
        field_name: str,
        old_value: str | None,
        new_value: str | None,
        change_type: str,
        changed_by: str
    ) -> None:
        """Log a change to the audit table."""
        cursor.execute("""
            INSERT INTO patient_change_log (id, patient_id, field_name, old_value, new_value, change_type, changed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), patient_id, field_name, old_value, new_value, change_type, changed_by))

    def _row_to_patient(self, row) -> Patient:
        """Convert a database row to a Patient object."""
        return Patient(
            id=row["id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            date_of_birth=row["date_of_birth"],
            phone=row["phone"],
            email=row["email"],
            address_line1=row["address_line1"],
            address_line2=row["address_line2"],
            city=row["city"],
            state=row["state"],
            zip_code=row["zip_code"],
            address_validated=bool(row["address_validated"]),
            insurance_payer=row["insurance_payer"],
            insurance_plan=row["insurance_plan"],
            insurance_member_id=row["insurance_member_id"],
            insurance_group_id=row["insurance_group_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_visit(self, row) -> Visit:
        """Convert a database row to a Visit object."""
        return Visit(
            id=row["id"],
            patient_id=row["patient_id"],
            chief_complaint=row["chief_complaint"],
            symptoms=row["symptoms"],
            symptom_duration=row["symptom_duration"],
            severity=row["severity"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
