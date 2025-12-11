"""End-to-end conversation flow simulation tests.

These tests simulate complete user journeys through the chatbot,
verifying state transitions and responses at each step.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from assort_intake_bot.state_machine import State, ConversationState, get_next_state
from assort_intake_bot.main import process_input, save_patient_data
from assort_intake_bot.conversation import generate_greeting, generate_response
from assort_intake_bot.patient_intake.database import init_database
from assort_intake_bot.patient_intake.database.connection import get_connection


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Initialize database before tests."""
    init_database()
    yield


@pytest.fixture
def test_provider_with_slots():
    """Create a test provider with available slots for flow tests."""
    conn = get_connection()
    provider_id = "prov-flow-test"

    # Cleanup
    conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
    conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

    # Create provider
    conn.execute(
        """INSERT INTO providers
           (id, name, specialty, insurance_accepted, conditions_treated, rating, accepting_new_patients)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            provider_id,
            "Dr. Flow Test",
            "Family Medicine",
            '["Blue Cross PPO", "Aetna HMO"]',
            '["back pain", "headache", "general checkup"]',
            4.8,
            1,
        ),
    )

    # Create available slots
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    for i, time in enumerate(["09:00", "10:00", "11:00", "14:00", "15:00"]):
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (f"slot-flow-{i}", provider_id, tomorrow, time, "available"),
        )
    conn.commit()
    conn.close()

    yield {
        "provider_id": provider_id,
        "name": "Dr. Flow Test",
        "tomorrow": tomorrow,
    }

    # Cleanup
    conn = get_connection()
    conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
    conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    conn.commit()
    conn.close()


def create_mock_extract_slots(data):
    """Create a mock ExtractedSlots response."""
    from assort_intake_bot.slot_extractor import ExtractedSlots
    return ExtractedSlots(**data)


def create_mock_intent(affirmative=False, negative=False, wants_update=False):
    """Create a mock UserIntent response."""
    from assort_intake_bot.slot_extractor import UserIntent
    return UserIntent(
        is_affirmative=affirmative,
        is_negative=negative,
        wants_to_update=wants_update,
        is_greeting=False,
    )


class TestNewPatientCompleteFlow:
    """Test complete flow for a new patient."""

    @patch("assort_intake_bot.main.extract_slots")
    @patch("assort_intake_bot.main.classify_intent")
    def test_new_patient_full_journey(self, mock_intent, mock_extract, test_provider_with_slots):
        """Test complete journey: new patient -> collect all info -> book appointment."""
        state = ConversationState()

        # Step 1: Greeting - user says they haven't been here
        state.current_state = State.CHECK_PATIENT
        mock_extract.return_value = create_mock_extract_slots({})
        mock_intent.return_value = create_mock_intent(negative=True)

        response = process_input(state, "No, I'm a new patient")

        assert state.current_state == State.COLLECT_PATIENT

        # Step 2: Provide patient info
        mock_extract.return_value = create_mock_extract_slots({
            "first_name": "Jane",
            "last_name": "Smith",
            "date_of_birth": "1988-05-20",
            "phone": "5559876543",
        })

        response = process_input(state, "Jane Smith, born May 20 1988, phone 555-987-6543")

        assert state.slots["first_name"] == "Jane"
        assert state.slots["last_name"] == "Smith"
        assert state.current_state == State.CONFIRM_PATIENT

        # Step 3: Confirm patient info
        mock_intent.return_value = create_mock_intent(affirmative=True)
        mock_extract.return_value = create_mock_extract_slots({})

        response = process_input(state, "yes")

        assert state.current_state == State.COLLECT_INSURANCE

        # Step 4: Provide insurance info
        mock_extract.return_value = create_mock_extract_slots({
            "insurance_payer": "Blue Cross",
            "insurance_member_id": "BC987654",
        })

        response = process_input(state, "Blue Cross, member ID BC987654")

        assert state.slots["insurance_payer"] == "Blue Cross"
        assert state.current_state == State.CONFIRM_INSURANCE

        # Step 5: Confirm insurance
        mock_intent.return_value = create_mock_intent(affirmative=True)
        mock_extract.return_value = create_mock_extract_slots({})

        response = process_input(state, "yes")

        assert state.current_state == State.COLLECT_ADDRESS

        # Step 6: Provide address
        mock_extract.return_value = create_mock_extract_slots({
            "address_line1": "456 Oak Street",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94110",
        })

        with patch("assort_intake_bot.main.validate_address") as mock_validate:
            mock_validate.return_value = MagicMock(
                is_valid=True,
                corrected_components=None,
            )
            response = process_input(state, "456 Oak Street, San Francisco CA 94110")

        assert state.slots["address_line1"] == "456 Oak Street"
        assert state.current_state == State.CONFIRM_ADDRESS

        # Step 7: Confirm address
        mock_intent.return_value = create_mock_intent(affirmative=True)
        mock_extract.return_value = create_mock_extract_slots({})

        response = process_input(state, "yes")

        assert state.current_state == State.COLLECT_MEDICAL

        # Step 8: Provide medical info - automatically queries providers
        mock_extract.return_value = create_mock_extract_slots({
            "chief_complaint": "back pain",
        })

        response = process_input(state, "I have back pain")

        assert state.slots["chief_complaint"] == "back pain"
        # After medical info, it auto-queries providers and transitions to SELECT_PROVIDER
        assert state.current_state == State.SELECT_PROVIDER
        assert len(state.matched_providers) > 0

        # Step 10: Select provider
        response = process_input(state, "1")

        assert state.selected_provider_id is not None
        assert state.current_state == State.SELECT_TIME
        assert len(state.available_slots) > 0

        # Step 11: Select time
        response = process_input(state, "1")

        assert state.selected_appointment_id is not None
        assert state.current_state == State.CONFIRM

        # Step 12: Final confirmation
        mock_intent.return_value = create_mock_intent(affirmative=True)

        response = process_input(state, "yes")

        assert state.current_state == State.END


class TestReturningPatientFlow:
    """Test flow for returning patients."""

    @patch("assort_intake_bot.main.extract_slots")
    @patch("assort_intake_bot.main.classify_intent")
    @patch("assort_intake_bot.main.repo")
    def test_returning_patient_no_updates(self, mock_repo, mock_intent, mock_extract, test_provider_with_slots):
        """Test returning patient who doesn't need to update info."""
        state = ConversationState()

        # Mock existing patient
        mock_patient = MagicMock()
        mock_patient.id = "p-existing"
        mock_patient.first_name = "John"
        mock_patient.last_name = "Doe"
        mock_patient.date_of_birth = "1985-03-15"
        mock_patient.phone = "5551234567"
        mock_patient.email = "john@example.com"
        mock_patient.address_line1 = "123 Main St"
        mock_patient.address_line2 = None
        mock_patient.city = "San Francisco"
        mock_patient.state = "CA"
        mock_patient.zip_code = "94102"
        mock_patient.address_validated = True
        mock_patient.insurance_payer = "Blue Cross"
        mock_patient.insurance_plan = "PPO"
        mock_patient.insurance_member_id = "BC123456"
        mock_patient.insurance_group_id = None

        mock_repo.find_existing_patient.return_value = mock_patient
        mock_repo.get_patient_summary.return_value = {
            "id": "p-existing",
            "name": "John Doe",
            "first_name": "John",
            "phone": "5551234567",
            "has_insurance": True,
            "insurance_payer": "Blue Cross",
            "recent_complaints": ["headache"],
            "visit_count": 3,
        }

        # Step 1: Check patient - found as returning
        state.current_state = State.CHECK_PATIENT
        mock_extract.return_value = create_mock_extract_slots({"phone": "5551234567"})

        response = process_input(state, "My phone is 555-123-4567")

        assert state.is_returning == True
        assert state.patient_id == "p-existing"
        assert state.current_state == State.CONFIRM_RETURNING
        assert "Welcome back" in response

        # Step 2: Confirm info is same
        mock_intent.return_value = create_mock_intent(affirmative=True)
        mock_extract.return_value = create_mock_extract_slots({})

        response = process_input(state, "Yes, everything is the same")

        assert state.current_state == State.COLLECT_MEDICAL

        # Step 3: Provide medical reason - automatically queries providers
        mock_extract.return_value = create_mock_extract_slots({
            "chief_complaint": "headache",
        })

        response = process_input(state, "I have a bad headache")

        # After medical info, it auto-queries providers and transitions to SELECT_PROVIDER
        assert state.current_state == State.SELECT_PROVIDER
        assert len(state.matched_providers) > 0

    @patch("assort_intake_bot.main.extract_slots")
    @patch("assort_intake_bot.main.classify_intent")
    @patch("assort_intake_bot.main.repo")
    def test_returning_patient_with_updates(self, mock_repo, mock_intent, mock_extract, test_provider_with_slots):
        """Test returning patient who updates their phone number."""
        state = ConversationState()

        # Mock existing patient
        mock_patient = MagicMock()
        mock_patient.id = "p-existing"
        mock_patient.first_name = "Jane"
        mock_patient.last_name = "Doe"
        mock_patient.date_of_birth = "1990-01-01"
        mock_patient.phone = "5551111111"
        mock_patient.email = None
        mock_patient.address_line1 = "789 Pine St"
        mock_patient.address_line2 = None
        mock_patient.city = "Oakland"
        mock_patient.state = "CA"
        mock_patient.zip_code = "94612"
        mock_patient.address_validated = True
        mock_patient.insurance_payer = "Aetna"
        mock_patient.insurance_plan = "HMO"
        mock_patient.insurance_member_id = "AET789"
        mock_patient.insurance_group_id = None

        mock_repo.find_existing_patient.return_value = mock_patient
        mock_repo.get_patient_summary.return_value = {
            "id": "p-existing",
            "name": "Jane Doe",
            "first_name": "Jane",
            "phone": "5551111111",
            "has_insurance": True,
            "insurance_payer": "Aetna",
            "recent_complaints": [],
            "visit_count": 1,
        }

        # Step 1: Check patient
        state.current_state = State.CHECK_PATIENT
        mock_extract.return_value = create_mock_extract_slots({"phone": "5551111111"})

        response = process_input(state, "5551111111")

        assert state.is_returning == True
        assert state.current_state == State.CONFIRM_RETURNING

        # Step 2: Update phone number
        mock_intent.return_value = create_mock_intent(wants_update=True)
        mock_extract.return_value = create_mock_extract_slots({"phone": "5552222222"})

        response = process_input(state, "I have a new phone number: 555-222-2222")

        assert state.slots["phone"] == "5552222222"
        assert "phone" in response.lower() or "update" in response.lower()

        # Step 3: Confirm done updating
        mock_intent.return_value = create_mock_intent(affirmative=True)
        mock_extract.return_value = create_mock_extract_slots({})

        response = process_input(state, "yes, that's all")

        assert state.current_state == State.COLLECT_MEDICAL


class TestAddressValidationFlow:
    """Test address validation scenarios."""

    @patch("assort_intake_bot.main.extract_slots")
    @patch("assort_intake_bot.main.classify_intent")
    @patch("assort_intake_bot.main.validate_address")
    def test_address_validation_success(self, mock_validate, mock_intent, mock_extract):
        """Test successful address validation."""
        state = ConversationState()
        state.current_state = State.COLLECT_ADDRESS
        state.slots["first_name"] = "Test"
        state.slots["last_name"] = "User"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["insurance_member_id"] = "BC123"

        mock_extract.return_value = create_mock_extract_slots({
            "address_line1": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94102",
        })
        mock_validate.return_value = MagicMock(
            is_valid=True,
            corrected_components=None,
            input_address="123 Main St, San Francisco, CA 94102",
        )

        response = process_input(state, "123 Main St, San Francisco CA 94102")

        assert state.slots["address_validated"] == True
        assert state.current_state == State.CONFIRM_ADDRESS

    @patch("assort_intake_bot.main.extract_slots")
    @patch("assort_intake_bot.main.classify_intent")
    @patch("assort_intake_bot.main.validate_address")
    def test_address_validation_with_correction(self, mock_validate, mock_intent, mock_extract):
        """Test address validation that corrects the address."""
        state = ConversationState()
        state.current_state = State.COLLECT_ADDRESS
        state.slots["first_name"] = "Test"
        state.slots["last_name"] = "User"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["insurance_member_id"] = "BC123"

        mock_extract.return_value = create_mock_extract_slots({
            "address_line1": "123 Main Street",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94102",
        })
        mock_validate.return_value = MagicMock(
            is_valid=True,
            corrected_components={"address_line1": "123 Main St"},
            input_address="123 Main Street, San Francisco, CA 94102",
        )

        response = process_input(state, "123 Main Street, San Francisco CA 94102")

        # Corrected address should be stored
        assert state.slots["address_line1"] == "123 Main St"
        assert state.slots["address_validated"] == True

    @patch("assort_intake_bot.main.extract_slots")
    @patch("assort_intake_bot.main.classify_intent")
    @patch("assort_intake_bot.main.validate_address")
    def test_address_validation_failure_retry(self, mock_validate, mock_intent, mock_extract):
        """Test address validation failure with suggested correction."""
        state = ConversationState()
        state.current_state = State.COLLECT_ADDRESS
        state.slots["first_name"] = "Test"
        state.slots["last_name"] = "User"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["insurance_member_id"] = "BC123"

        mock_extract.return_value = create_mock_extract_slots({
            "address_line1": "123 Mian St",  # Typo
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94102",
        })
        mock_validate.return_value = MagicMock(
            is_valid=False,
            suggested_address="123 Main St, San Francisco, CA 94102, USA",
            input_address="123 Mian St, San Francisco, CA 94102",
            corrected_components=None,
        )

        response = process_input(state, "123 Mian St, San Francisco CA 94102")

        assert state.current_state == State.VALIDATE_ADDRESS
        assert state.pending_address_suggestion == "123 Main St, San Francisco, CA 94102, USA"
        assert "Did you mean" in response

        # User accepts suggestion
        mock_intent.return_value = create_mock_intent(affirmative=True)
        mock_extract.return_value = create_mock_extract_slots({})

        response = process_input(state, "yes")

        assert state.slots["address_validated"] == True
        assert state.current_state == State.CONFIRM_ADDRESS


class TestStateMachineTransitions:
    """Test state machine transitions."""

    def test_full_state_sequence_new_patient(self):
        """Test expected state sequence for new patient."""
        state = ConversationState()

        # GREET -> CHECK_PATIENT
        state.current_state = State.GREET
        assert get_next_state(state) == State.CHECK_PATIENT

        # CHECK_PATIENT -> COLLECT_PATIENT (new patient)
        state.current_state = State.CHECK_PATIENT
        state.is_returning = False
        assert get_next_state(state) == State.COLLECT_PATIENT

        # COLLECT_PATIENT -> stays until complete
        state.current_state = State.COLLECT_PATIENT
        assert get_next_state(state) == State.COLLECT_PATIENT

        # COLLECT_PATIENT -> CONFIRM_PATIENT when complete
        state.slots["first_name"] = "John"
        state.slots["last_name"] = "Doe"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        assert get_next_state(state) == State.CONFIRM_PATIENT

        # CONFIRM_PATIENT -> COLLECT_INSURANCE
        state.current_state = State.CONFIRM_PATIENT
        assert get_next_state(state) == State.COLLECT_INSURANCE

        # COLLECT_INSURANCE -> CONFIRM_INSURANCE when complete
        state.current_state = State.COLLECT_INSURANCE
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["insurance_member_id"] = "BC123"
        assert get_next_state(state) == State.CONFIRM_INSURANCE

        # CONFIRM_INSURANCE -> COLLECT_ADDRESS
        state.current_state = State.CONFIRM_INSURANCE
        assert get_next_state(state) == State.COLLECT_ADDRESS

        # COLLECT_ADDRESS -> VALIDATE_ADDRESS when complete
        state.current_state = State.COLLECT_ADDRESS
        state.slots["address_line1"] = "123 Main St"
        state.slots["city"] = "San Francisco"
        state.slots["state"] = "CA"
        state.slots["zip_code"] = "94102"
        assert get_next_state(state) == State.VALIDATE_ADDRESS

        # VALIDATE_ADDRESS -> CONFIRM_ADDRESS when validated
        state.current_state = State.VALIDATE_ADDRESS
        state.slots["address_validated"] = True
        assert get_next_state(state) == State.CONFIRM_ADDRESS

        # CONFIRM_ADDRESS -> COLLECT_MEDICAL
        state.current_state = State.CONFIRM_ADDRESS
        assert get_next_state(state) == State.COLLECT_MEDICAL

        # COLLECT_MEDICAL -> QUERY_PROVIDERS when complete
        state.current_state = State.COLLECT_MEDICAL
        state.slots["chief_complaint"] = "back pain"
        assert get_next_state(state) == State.QUERY_PROVIDERS

        # QUERY_PROVIDERS -> SELECT_PROVIDER when providers found
        state.current_state = State.QUERY_PROVIDERS
        state.matched_providers = [{"id": "prov-1", "name": "Dr. Test"}]
        assert get_next_state(state) == State.SELECT_PROVIDER

        # SELECT_PROVIDER -> SELECT_TIME when provider selected
        state.current_state = State.SELECT_PROVIDER
        state.selected_provider_id = "prov-1"
        assert get_next_state(state) == State.SELECT_TIME

        # SELECT_TIME -> CONFIRM when time selected
        state.current_state = State.SELECT_TIME
        state.selected_appointment_id = "slot-1"
        assert get_next_state(state) == State.CONFIRM

        # CONFIRM -> END
        state.current_state = State.CONFIRM
        assert get_next_state(state) == State.END

    def test_returning_patient_state_sequence(self):
        """Test state sequence for returning patient."""
        state = ConversationState()

        # CHECK_PATIENT -> CONFIRM_RETURNING for returning patient
        state.current_state = State.CHECK_PATIENT
        state.is_returning = True
        assert get_next_state(state) == State.CONFIRM_RETURNING

        # CONFIRM_RETURNING -> COLLECT_MEDICAL
        state.current_state = State.CONFIRM_RETURNING
        assert get_next_state(state) == State.COLLECT_MEDICAL


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_user_input(self):
        """Test handling empty input."""
        state = ConversationState()
        state.current_state = State.COLLECT_PATIENT

        # Empty input should still get a response
        response = generate_response(state, "")
        assert response  # Should not be empty

    def test_unknown_state_handler(self):
        """Test handling unknown state."""
        state = ConversationState()
        state.current_state = State.END

        response = process_input(state, "hello")

        # Should handle gracefully
        assert "wrong" in response.lower() or response

    @patch("assort_intake_bot.main.extract_slots")
    def test_partial_slot_extraction(self, mock_extract):
        """Test handling partial slot extraction."""
        state = ConversationState()
        state.current_state = State.COLLECT_PATIENT

        # Only extracts first name
        mock_extract.return_value = create_mock_extract_slots({
            "first_name": "John",
        })

        response = process_input(state, "My name is John")

        assert state.slots["first_name"] == "John"
        assert state.slots["last_name"] is None
        assert state.current_state == State.COLLECT_PATIENT  # Stays in same state

    def test_provider_selection_with_no_slots(self, test_provider_with_slots):
        """Test provider selection when provider has no available slots."""
        conn = get_connection()
        provider_id = "prov-no-slots"

        # Create provider without slots
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.execute(
            """INSERT INTO providers (id, name, specialty, rating, accepting_new_patients)
               VALUES (?, ?, ?, ?, ?)""",
            (provider_id, "Dr. No Slots", "Family Medicine", 4.0, 1),
        )
        conn.commit()
        conn.close()

        state = ConversationState()
        state.current_state = State.SELECT_PROVIDER
        state.matched_providers = [
            {"id": provider_id, "name": "Dr. No Slots", "specialty": "Family Medicine", "rating": 4.0},
        ]

        from assort_intake_bot.main import handle_select_provider
        response = handle_select_provider(state, "1")

        # Should stay in SELECT_PROVIDER and show message about no slots
        assert "no" in response.lower() or "another" in response.lower()

        # Cleanup
        conn = get_connection()
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()
        conn.close()
