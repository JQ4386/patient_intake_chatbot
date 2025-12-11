"""State machine for patient intake workflow."""

from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    """States in the patient intake workflow."""
    GREET = "greet"
    CHECK_PATIENT = "check_patient"
    VERIFY_DOB = "verify_dob"
    CONFIRM_RETURNING = "confirm_returning"
    COLLECT_PATIENT = "collect_patient"
    CONFIRM_PATIENT = "confirm_patient"
    COLLECT_INSURANCE = "collect_insurance"
    CONFIRM_INSURANCE = "confirm_insurance"
    COLLECT_ADDRESS = "collect_address"
    VALIDATE_ADDRESS = "validate_address"
    CONFIRM_ADDRESS = "confirm_address"
    COLLECT_MEDICAL = "collect_medical"
    QUERY_PROVIDERS = "query_providers"
    SELECT_PROVIDER = "select_provider"
    SELECT_TIME = "select_time"
    CONFIRM = "confirm"
    END = "end"


# Required slots for each collection phase
PHASE_REQUIREMENTS = {
    State.COLLECT_PATIENT: ["first_name", "last_name", "date_of_birth", "phone"],
    State.COLLECT_INSURANCE: ["insurance_payer", "insurance_member_id"],
    State.COLLECT_ADDRESS: ["address_line1", "city", "state", "zip_code"],
    State.COLLECT_MEDICAL: ["chief_complaint"],
}


@dataclass
class ConversationState:
    """Tracks the full state of an intake conversation."""
    current_state: State = State.GREET

    # Patient identification
    patient_id: str | None = None
    is_returning: bool = False

    # All collected slots (mirrors Patient fields from repository)
    slots: dict = field(default_factory=lambda: {
        # Patient info
        "first_name": None,
        "last_name": None,
        "date_of_birth": None,
        "phone": None,
        "email": None,
        # Address
        "address_line1": None,
        "address_line2": None,
        "city": None,
        "state": None,
        "zip_code": None,
        "address_validated": False,
        # Insurance
        "insurance_payer": None,
        "insurance_plan": None,
        "insurance_member_id": None,
        "insurance_group_id": None,
        # Medical
        "chief_complaint": None,
        "symptoms": None,
        "symptom_duration": None,
        "severity": None,
    })

    # Address validation retry count
    address_validation_attempts: int = 0

    # Pending address suggestion from validation
    pending_address_suggestion: str | None = None

    # Pending name matches awaiting DOB verification
    pending_name_matches: list = field(default_factory=list)

    # Provider selection
    matched_providers: list = field(default_factory=list)
    selected_provider_id: str | None = None
    selected_provider_name: str | None = None

    # Appointment selection
    available_slots: list = field(default_factory=list)
    selected_appointment_id: str | None = None
    selected_date: str | None = None
    selected_time: str | None = None

    # Conversation history for LLM context
    messages: list = field(default_factory=list)

    def get_missing_slots(self, phase: State) -> list[str]:
        """Get unfilled or invalid required slots for a phase."""
        if phase not in PHASE_REQUIREMENTS:
            return []
        missing = []
        for slot in PHASE_REQUIREMENTS[phase]:
            value = self.slots.get(slot)
            if not value or not self._is_valid_slot(slot, value):
                missing.append(slot)
        return missing

    def _is_valid_slot(self, slot: str, value) -> bool:
        """Check if a slot value is valid (present and correct type)."""
        if not value:
            return False
        if slot == "phone":
            # Phone just needs to have some digits
            digits = str(value)
            return len(digits) > 0 and digits.replace("-", "").replace(" ", "").isdigit()
        if slot == "date_of_birth":
            # DOB should be in YYYY-MM-DD format
            import re
            return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value)))
        if slot == "zip_code":
            # ZIP just needs to be numeric
            return str(value).isdigit()
        return True

    def get_invalid_slots(self, phase: State) -> dict[str, str]:
        """Get slots that have values but are invalid, with error messages."""
        # No strict validation - just check presence
        return {}

    def is_phase_complete(self, phase: State) -> bool:
        """Check if all required slots for a phase are filled and valid."""
        return len(self.get_missing_slots(phase)) == 0

    def merge_slots(self, extracted: dict) -> list[str]:
        """Merge extracted slots into state. Returns list of changed slots."""
        changed = []
        for key, value in extracted.items():
            if value is not None and key in self.slots:
                if self.slots[key] != value:
                    changed.append(key)
                    self.slots[key] = value
        return changed


def get_next_state(state: ConversationState) -> State:
    """Determine the next state based on current state and slot completion."""
    current = state.current_state

    if current == State.GREET:
        return State.CHECK_PATIENT

    if current == State.CHECK_PATIENT:
        if state.is_returning:
            return State.CONFIRM_RETURNING
        return State.COLLECT_PATIENT

    if current == State.CONFIRM_RETURNING:
        # After confirming/updating, go to medical collection
        return State.COLLECT_MEDICAL

    if current == State.COLLECT_PATIENT:
        if state.is_phase_complete(State.COLLECT_PATIENT):
            return State.CONFIRM_PATIENT
        return State.COLLECT_PATIENT

    if current == State.CONFIRM_PATIENT:
        return State.COLLECT_INSURANCE

    if current == State.COLLECT_INSURANCE:
        if state.is_phase_complete(State.COLLECT_INSURANCE):
            return State.CONFIRM_INSURANCE
        return State.COLLECT_INSURANCE

    if current == State.CONFIRM_INSURANCE:
        return State.COLLECT_ADDRESS

    if current == State.COLLECT_ADDRESS:
        if state.is_phase_complete(State.COLLECT_ADDRESS):
            return State.VALIDATE_ADDRESS
        return State.COLLECT_ADDRESS

    if current == State.VALIDATE_ADDRESS:
        if state.slots.get("address_validated") is not None:
            return State.CONFIRM_ADDRESS
        # Address invalid, go back to collect
        return State.COLLECT_ADDRESS

    if current == State.CONFIRM_ADDRESS:
        return State.COLLECT_MEDICAL

    if current == State.COLLECT_MEDICAL:
        if state.is_phase_complete(State.COLLECT_MEDICAL):
            return State.QUERY_PROVIDERS
        return State.COLLECT_MEDICAL

    if current == State.QUERY_PROVIDERS:
        if state.matched_providers:
            return State.SELECT_PROVIDER
        return State.QUERY_PROVIDERS

    if current == State.SELECT_PROVIDER:
        if state.selected_provider_id:
            return State.SELECT_TIME
        return State.SELECT_PROVIDER

    if current == State.SELECT_TIME:
        if state.selected_appointment_id:
            return State.CONFIRM
        return State.SELECT_TIME

    if current == State.CONFIRM:
        return State.END

    return State.END
