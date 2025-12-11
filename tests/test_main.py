"""Tests for main chatbot module."""

from assort_intake_bot.state_machine import State, ConversationState, get_next_state
from assort_intake_bot.conversation import generate_greeting, generate_response


class TestStateMachine:
    """Tests for state machine transitions."""

    def test_initial_state(self):
        """Test that conversation starts in GREET state."""
        state = ConversationState()
        assert state.current_state == State.GREET

    def test_greet_to_check_patient(self):
        """Test transition from GREET to CHECK_PATIENT."""
        state = ConversationState()
        state.current_state = State.GREET
        next_state = get_next_state(state)
        assert next_state == State.CHECK_PATIENT

    def test_new_patient_flow(self):
        """Test new patient goes to COLLECT_PATIENT."""
        state = ConversationState()
        state.current_state = State.CHECK_PATIENT
        state.is_returning = False
        next_state = get_next_state(state)
        assert next_state == State.COLLECT_PATIENT

    def test_returning_patient_flow(self):
        """Test returning patient goes to CONFIRM_RETURNING."""
        state = ConversationState()
        state.current_state = State.CHECK_PATIENT
        state.is_returning = True
        next_state = get_next_state(state)
        assert next_state == State.CONFIRM_RETURNING

    def test_collect_patient_incomplete(self):
        """Test COLLECT_PATIENT stays if incomplete."""
        state = ConversationState()
        state.current_state = State.COLLECT_PATIENT
        state.slots["first_name"] = "John"
        # Missing last_name, dob, phone
        next_state = get_next_state(state)
        assert next_state == State.COLLECT_PATIENT

    def test_collect_patient_complete(self):
        """Test COLLECT_PATIENT advances when complete."""
        state = ConversationState()
        state.current_state = State.COLLECT_PATIENT
        state.slots["first_name"] = "John"
        state.slots["last_name"] = "Doe"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        next_state = get_next_state(state)
        assert next_state == State.CONFIRM_PATIENT  # Goes to confirmation before insurance


class TestConversationState:
    """Tests for ConversationState methods."""

    def test_merge_slots(self):
        """Test merging extracted slots."""
        state = ConversationState()
        newly_filled = state.merge_slots({
            "first_name": "John",
            "last_name": "Doe",
        })
        assert "first_name" in newly_filled
        assert "last_name" in newly_filled
        assert state.slots["first_name"] == "John"
        assert state.slots["last_name"] == "Doe"

    def test_merge_slots_overwrites(self):
        """Test that merge overwrites existing values and returns changed slots."""
        state = ConversationState()
        state.slots["first_name"] = "John"
        changed = state.merge_slots({"first_name": "Jane"})
        # Slot was changed (overwritten), so it appears in changed list
        assert "first_name" in changed
        assert state.slots["first_name"] == "Jane"

    def test_merge_slots_same_value_not_changed(self):
        """Test that merge doesn't report unchanged when value is same."""
        state = ConversationState()
        state.slots["first_name"] = "John"
        changed = state.merge_slots({"first_name": "John"})
        # Value is the same, so no change reported
        assert "first_name" not in changed
        assert state.slots["first_name"] == "John"

    def test_get_missing_slots(self):
        """Test getting missing required slots."""
        state = ConversationState()
        state.slots["first_name"] = "John"
        missing = state.get_missing_slots(State.COLLECT_PATIENT)
        assert "first_name" not in missing
        assert "last_name" in missing
        assert "date_of_birth" in missing
        assert "phone" in missing

    def test_is_phase_complete(self):
        """Test phase completion check."""
        state = ConversationState()
        assert not state.is_phase_complete(State.COLLECT_PATIENT)

        state.slots["first_name"] = "John"
        state.slots["last_name"] = "Doe"
        state.slots["date_of_birth"] = "1990-01-01"
        state.slots["phone"] = "5551234567"
        assert state.is_phase_complete(State.COLLECT_PATIENT)


class TestConversation:
    """Tests for conversation generation."""

    def test_generate_greeting(self):
        """Test greeting message generation."""
        greeting = generate_greeting()
        assert "Welcome" in greeting
        assert "Assort Health" in greeting

    def test_generate_response_collect_patient(self):
        """Test response generation for patient collection."""
        state = ConversationState()
        state.current_state = State.COLLECT_PATIENT
        response = generate_response(state, "hello")
        assert "name" in response.lower() or "phone" in response.lower()
