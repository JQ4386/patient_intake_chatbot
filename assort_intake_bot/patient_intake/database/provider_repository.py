"""Provider and appointment repository with query operations."""

import json
from dataclasses import dataclass
from datetime import datetime

from .connection import get_connection


@dataclass
class Provider:
    id: str
    name: str
    specialty: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    insurance_accepted: list[str] | None = None
    conditions_treated: list[str] | None = None
    rating: float = 0.0
    available_days: list[str] | None = None
    hours_start: str | None = None
    hours_end: str | None = None
    accepting_new_patients: bool = True


@dataclass
class Appointment:
    id: str
    provider_id: str
    date: str
    time: str
    status: str = "available"
    patient_id: str | None = None
    visit_id: str | None = None
    reason: str | None = None
    notes: str | None = None
    booked_at: str | None = None


class ProviderRepository:
    """Repository for provider and appointment operations."""

    def find_providers(
        self,
        insurance: str | None = None,
        condition: str | None = None,
        specialty: str | None = None,
        limit: int = 5,
    ) -> list[Provider]:
        """Find providers matching criteria."""
        conn = get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM providers WHERE accepting_new_patients = 1"
        params = []

        if insurance:
            query += " AND insurance_accepted LIKE ?"
            params.append(f"%{insurance}%")

        if condition:
            query += " AND conditions_treated LIKE ?"
            params.append(f"%{condition}%")

        if specialty:
            query += " AND specialty LIKE ?"
            params.append(f"%{specialty}%")

        query += " ORDER BY rating DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_provider(row) for row in rows]

    def get_by_id(self, provider_id: str) -> Provider | None:
        """Get a provider by ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM providers WHERE id = ?", (provider_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_provider(row) if row else None

    def get_available_slots(
        self,
        provider_id: str,
        from_date: str | None = None,
        limit: int = 10,
    ) -> list[Appointment]:
        """Get available appointment slots for a provider."""
        conn = get_connection()
        cursor = conn.cursor()

        if from_date is None:
            from_date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            """SELECT * FROM appointments
               WHERE provider_id = ?
                 AND patient_id IS NULL
                 AND status = 'available'
                 AND date >= ?
               ORDER BY date, time
               LIMIT ?""",
            (provider_id, from_date, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_appointment(row) for row in rows]

    def get_appointment_by_id(self, appointment_id: str) -> Appointment | None:
        """Get an appointment by ID."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_appointment(row) if row else None

    def book_appointment(
        self,
        appointment_id: str,
        patient_id: str,
        visit_id: str | None = None,
        reason: str | None = None,
    ) -> Appointment | None:
        """Book an available appointment slot."""
        conn = get_connection()
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        # Only book if slot is available
        cursor.execute(
            """UPDATE appointments
               SET patient_id = ?, visit_id = ?, status = 'booked',
                   reason = ?, booked_at = ?
               WHERE id = ? AND patient_id IS NULL AND status = 'available'""",
            (patient_id, visit_id, reason, now, appointment_id),
        )

        if cursor.rowcount == 0:
            conn.close()
            return None

        conn.commit()
        conn.close()

        return self.get_appointment_by_id(appointment_id)

    def _row_to_provider(self, row) -> Provider:
        """Convert a database row to a Provider object."""
        return Provider(
            id=row["id"],
            name=row["name"],
            specialty=row["specialty"],
            address=row["address"],
            phone=row["phone"],
            email=row["email"],
            insurance_accepted=json.loads(row["insurance_accepted"]) if row["insurance_accepted"] else None,
            conditions_treated=json.loads(row["conditions_treated"]) if row["conditions_treated"] else None,
            rating=row["rating"] or 0.0,
            available_days=json.loads(row["available_days"]) if row["available_days"] else None,
            hours_start=row["hours_start"],
            hours_end=row["hours_end"],
            accepting_new_patients=bool(row["accepting_new_patients"]),
        )

    def _row_to_appointment(self, row) -> Appointment:
        """Convert a database row to an Appointment object."""
        return Appointment(
            id=row["id"],
            provider_id=row["provider_id"],
            date=row["date"],
            time=row["time"],
            status=row["status"],
            patient_id=row["patient_id"],
            visit_id=row["visit_id"],
            reason=row["reason"],
            notes=row["notes"],
            booked_at=row["booked_at"],
        )
