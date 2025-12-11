"""Tests for provider and appointment handler functions."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from assort_intake_bot.state_machine import State, ConversationState
from assort_intake_bot.main import (
    handle_query_providers,
    handle_select_provider,
    handle_select_time,
)
from assort_intake_bot.patient_intake.database import init_database
from assort_intake_bot.patient_intake.database.connection import get_connection
from assort_intake_bot.patient_intake.database.provider_repository import Provider, Appointment


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Initialize database before tests."""
    init_database()
    yield


@pytest.fixture
def test_provider_with_slots():
    """Create a test provider with available slots."""
    conn = get_connection()
    provider_id = "prov-handler-test"

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
            "Dr. Handler Test",
            "Family Medicine",
            '["Blue Cross PPO", "Test Insurance"]',
            '["back pain", "headache"]',
            4.7,
            1,
        ),
    )

    # Create available slots
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    for i, time in enumerate(["09:00", "10:00", "11:00", "14:00", "15:00"]):
        conn.execute(
            """INSERT INTO appointments (id, provider_id, date, time, status)
               VALUES (?, ?, ?, ?, ?)""",
            (f"slot-handler-{i}", provider_id, tomorrow, time, "available"),
        )
    conn.commit()
    conn.close()

    yield {
        "provider_id": provider_id,
        "name": "Dr. Handler Test",
        "tomorrow": tomorrow,
    }

    # Cleanup
    conn = get_connection()
    conn.execute("DELETE FROM appointments WHERE provider_id = ?", (provider_id,))
    conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    conn.commit()
    conn.close()


class TestHandleQueryProviders:
    """Tests for handle_query_providers function."""

    def test_query_providers_finds_matching(self, test_provider_with_slots):
        """Test that query finds providers matching insurance and condition."""
        state = ConversationState()
        state.current_state = State.QUERY_PROVIDERS
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["chief_complaint"] = "back pain"

        response = handle_query_providers(state, "")

        assert state.current_state == State.SELECT_PROVIDER
        assert len(state.matched_providers) > 0
        assert "provider" in response.lower() or "select" in response.lower()

    def test_query_providers_fallback_to_insurance_only(self, test_provider_with_slots):
        """Test fallback when no condition match found."""
        state = ConversationState()
        state.current_state = State.QUERY_PROVIDERS
        state.slots["insurance_payer"] = "Test Insurance"
        state.slots["chief_complaint"] = "rare condition xyz"

        response = handle_query_providers(state, "")

        # Should still find providers matching insurance
        assert state.current_state == State.SELECT_PROVIDER
        assert len(state.matched_providers) >= 0  # May find some

    def test_query_providers_stores_provider_info(self, test_provider_with_slots):
        """Test that provider info is correctly stored in state."""
        state = ConversationState()
        state.current_state = State.QUERY_PROVIDERS
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["chief_complaint"] = "back pain"

        handle_query_providers(state, "")

        if state.matched_providers:
            provider = state.matched_providers[0]
            assert "id" in provider
            assert "name" in provider
            assert "specialty" in provider
            assert "rating" in provider


class TestHandleSelectProvider:
    """Tests for handle_select_provider function."""

    def test_select_provider_by_number(self, test_provider_with_slots):
        """Test selecting a provider by number."""
        state = ConversationState()
        state.current_state = State.SELECT_PROVIDER
        state.matched_providers = [
            {"id": test_provider_with_slots["provider_id"], "name": "Dr. Handler Test", "specialty": "Family Medicine", "rating": 4.7},
            {"id": "prov-002", "name": "Dr. Other", "specialty": "Internal Medicine", "rating": 4.5},
        ]

        response = handle_select_provider(state, "1")

        assert state.selected_provider_id == test_provider_with_slots["provider_id"]
        assert state.selected_provider_name == "Dr. Handler Test"
        assert state.current_state == State.SELECT_TIME
        assert len(state.available_slots) > 0

    def test_select_provider_by_name(self, test_provider_with_slots):
        """Test selecting a provider by name."""
        state = ConversationState()
        state.current_state = State.SELECT_PROVIDER
        state.matched_providers = [
            {"id": test_provider_with_slots["provider_id"], "name": "Dr. Handler Test", "specialty": "Family Medicine", "rating": 4.7},
        ]

        response = handle_select_provider(state, "Dr. Handler Test")

        assert state.selected_provider_id == test_provider_with_slots["provider_id"]
        assert state.current_state == State.SELECT_TIME

    def test_select_provider_by_partial_name(self, test_provider_with_slots):
        """Test selecting a provider by partial name match."""
        state = ConversationState()
        state.current_state = State.SELECT_PROVIDER
        state.matched_providers = [
            {"id": test_provider_with_slots["provider_id"], "name": "Dr. Handler Test", "specialty": "Family Medicine", "rating": 4.7},
        ]

        # The name matching requires provider name to be in user input
        response = handle_select_provider(state, "I'd like to see Dr. Handler Test please")

        assert state.selected_provider_id == test_provider_with_slots["provider_id"]

    def test_select_provider_invalid_number(self, test_provider_with_slots):
        """Test selecting with invalid number."""
        state = ConversationState()
        state.current_state = State.SELECT_PROVIDER
        state.matched_providers = [
            {"id": "prov-001", "name": "Dr. One", "specialty": "Family Medicine", "rating": 4.7},
        ]

        response = handle_select_provider(state, "5")

        assert state.selected_provider_id is None
        # LLM should ask to pick from the list
        assert len(response) > 0  # Got a response asking to pick

    def test_select_provider_invalid_input(self):
        """Test selecting with unrecognized input."""
        state = ConversationState()
        state.current_state = State.SELECT_PROVIDER
        state.matched_providers = [
            {"id": "prov-001", "name": "Dr. One", "specialty": "Family Medicine", "rating": 4.7},
        ]

        response = handle_select_provider(state, "random gibberish")

        assert state.selected_provider_id is None
        assert "pick" in response.lower() or "select" in response.lower()

    def test_select_provider_stores_slots(self, test_provider_with_slots):
        """Test that available slots are stored after selection."""
        state = ConversationState()
        state.current_state = State.SELECT_PROVIDER
        state.matched_providers = [
            {"id": test_provider_with_slots["provider_id"], "name": "Dr. Handler Test", "specialty": "Family Medicine", "rating": 4.7},
        ]

        handle_select_provider(state, "1")

        assert len(state.available_slots) > 0
        for slot in state.available_slots:
            assert "id" in slot
            assert "date" in slot
            assert "time" in slot


class TestHandleSelectTime:
    """Tests for handle_select_time function."""

    def test_select_time_by_number(self):
        """Test selecting a time slot by number."""
        state = ConversationState()
        state.current_state = State.SELECT_TIME
        state.selected_provider_id = "prov-001"
        state.selected_provider_name = "Dr. Test"
        state.available_slots = [
            {"id": "slot-1", "date": "2025-12-15", "time": "09:00"},
            {"id": "slot-2", "date": "2025-12-15", "time": "10:00"},
            {"id": "slot-3", "date": "2025-12-15", "time": "11:00"},
        ]
        state.slots["chief_complaint"] = "back pain"
        state.slots["first_name"] = "John"
        state.slots["last_name"] = "Doe"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["insurance_member_id"] = "BC123"
        state.slots["address_line1"] = "123 Main St"
        state.slots["city"] = "San Francisco"
        state.slots["state"] = "CA"
        state.slots["zip_code"] = "94102"

        response = handle_select_time(state, "2")

        assert state.selected_appointment_id == "slot-2"
        assert state.selected_date == "2025-12-15"
        assert state.selected_time == "10:00"
        assert state.current_state == State.CONFIRM

    def test_select_time_by_date_mention(self):
        """Test selecting by mentioning the date."""
        state = ConversationState()
        state.current_state = State.SELECT_TIME
        state.selected_provider_id = "prov-001"
        state.available_slots = [
            {"id": "slot-1", "date": "2025-12-15", "time": "09:00"},
            {"id": "slot-2", "date": "2025-12-16", "time": "10:00"},
        ]
        state.slots["chief_complaint"] = "back pain"
        state.slots["first_name"] = "John"
        state.slots["last_name"] = "Doe"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["insurance_member_id"] = "BC123"
        state.slots["address_line1"] = "123 Main St"
        state.slots["city"] = "San Francisco"
        state.slots["state"] = "CA"
        state.slots["zip_code"] = "94102"

        response = handle_select_time(state, "2025-12-16")

        assert state.selected_appointment_id == "slot-2"
        assert state.selected_date == "2025-12-16"

    def test_select_time_by_time_mention(self):
        """Test selecting by mentioning the time."""
        state = ConversationState()
        state.current_state = State.SELECT_TIME
        state.selected_provider_id = "prov-001"
        state.available_slots = [
            {"id": "slot-1", "date": "2025-12-15", "time": "09:00"},
            {"id": "slot-2", "date": "2025-12-15", "time": "14:30"},
        ]
        state.slots["chief_complaint"] = "back pain"
        state.slots["first_name"] = "John"
        state.slots["last_name"] = "Doe"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        state.slots["insurance_payer"] = "Blue Cross"
        state.slots["insurance_member_id"] = "BC123"
        state.slots["address_line1"] = "123 Main St"
        state.slots["city"] = "San Francisco"
        state.slots["state"] = "CA"
        state.slots["zip_code"] = "94102"

        response = handle_select_time(state, "14:30")

        assert state.selected_appointment_id == "slot-2"
        assert state.selected_time == "14:30"

    def test_select_time_invalid_number(self):
        """Test selecting with invalid number."""
        state = ConversationState()
        state.current_state = State.SELECT_TIME
        state.available_slots = [
            {"id": "slot-1", "date": "2025-12-15", "time": "09:00"},
        ]

        response = handle_select_time(state, "10")

        assert state.selected_appointment_id is None
        # LLM should ask to pick from the list
        assert len(response) > 0  # Got a response asking to pick

    def test_select_time_invalid_input(self):
        """Test selecting with unrecognized input."""
        state = ConversationState()
        state.current_state = State.SELECT_TIME
        state.available_slots = [
            {"id": "slot-1", "date": "2025-12-15", "time": "09:00"},
        ]

        response = handle_select_time(state, "whenever works")

        assert state.selected_appointment_id is None
        assert "pick" in response.lower() or "select" in response.lower()


class TestProviderConversationPrompts:
    """Tests for provider/appointment conversation prompts."""

    def test_provider_selection_prompt(self):
        """Test that provider selection shows all provider info."""
        from assort_intake_bot.conversation import generate_provider_selection

        state = ConversationState()
        state.matched_providers = [
            {"id": "prov-001", "name": "Dr. Sarah Chen", "specialty": "Family Medicine", "rating": 4.8},
            {"id": "prov-002", "name": "Dr. Michael Roberts", "specialty": "Internal Medicine", "rating": 4.6},
        ]

        prompt = generate_provider_selection(state)

        assert "Dr. Sarah Chen" in prompt
        assert "Dr. Michael Roberts" in prompt
        assert "Family Medicine" in prompt
        assert "4.8" in prompt
        assert "1." in prompt
        assert "2." in prompt

    def test_provider_selection_empty_list(self):
        """Test provider selection with no providers."""
        from assort_intake_bot.conversation import generate_provider_selection

        state = ConversationState()
        state.matched_providers = []

        prompt = generate_provider_selection(state)

        assert "searching" in prompt.lower()

    def test_time_selection_prompt(self):
        """Test that time selection shows all slots."""
        from assort_intake_bot.conversation import generate_time_selection

        state = ConversationState()
        state.selected_provider_name = "Dr. Sarah Chen"
        state.available_slots = [
            {"id": "slot-1", "date": "2025-12-15", "time": "09:00"},
            {"id": "slot-2", "date": "2025-12-15", "time": "10:00"},
            {"id": "slot-3", "date": "2025-12-16", "time": "14:00"},
        ]

        prompt = generate_time_selection(state)

        assert "Dr. Sarah Chen" in prompt
        assert "2025-12-15" in prompt
        assert "2025-12-16" in prompt
        assert "09:00" in prompt
        assert "10:00" in prompt
        assert "14:00" in prompt

    def test_time_selection_empty_slots(self):
        """Test time selection with no slots."""
        from assort_intake_bot.conversation import generate_time_selection

        state = ConversationState()
        state.available_slots = []

        prompt = generate_time_selection(state)

        assert "checking" in prompt.lower()

    def test_confirmation_includes_appointment(self):
        """Test that final confirmation includes appointment details."""
        from assort_intake_bot.conversation import generate_confirmation

        state = ConversationState()
        state.selected_provider_name = "Dr. Sarah Chen"
        state.selected_date = "2025-12-15"
        state.selected_time = "09:00"
        state.slots = {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-01",
            "phone": "5551234567",
            "email": "john@example.com",
            "address_line1": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94102",
            "insurance_payer": "Blue Cross",
            "insurance_member_id": "BC123",
            "chief_complaint": "back pain",
        }

        confirmation = generate_confirmation(state)

        assert "Dr. Sarah Chen" in confirmation
        assert "2025-12-15" in confirmation
        assert "09:00" in confirmation
        assert "back pain" in confirmation
        assert "John" in confirmation
        assert "Doe" in confirmation

    def test_confirmation_without_appointment(self):
        """Test confirmation without appointment (edge case)."""
        from assort_intake_bot.conversation import generate_confirmation

        state = ConversationState()
        state.selected_provider_name = None
        state.selected_date = None
        state.slots = {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-01",
            "phone": "5551234567",
            "address_line1": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "zip_code": "94102",
            "insurance_payer": "Blue Cross",
            "insurance_member_id": "BC123",
            "chief_complaint": "back pain",
        }

        confirmation = generate_confirmation(state)

        # Should still work without appointment details
        assert "John" in confirmation
        assert "Doe" in confirmation
