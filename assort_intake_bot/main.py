"""Patient intake chatbot with state machine workflow."""

import uuid
from rich.console import Console
from rich.markdown import Markdown
from rich.status import Status

from assort_intake_bot.state_machine import State, ConversationState, get_next_state
from assort_intake_bot.slot_extractor import extract_slots, classify_intent
from assort_intake_bot.conversation import (
    generate_greeting,
    generate_response,
    generate_end_message,
    generate_llm_response,
    interpret_selection,
)
from assort_intake_bot.address_validator import validate_address
from assort_intake_bot.patient_intake.database.connection import init_database
from assort_intake_bot.patient_intake.database.patient_repository import Patient, PatientRepository
from assort_intake_bot.patient_intake.database.provider_repository import ProviderRepository

console = Console()
repo = PatientRepository()
provider_repo = ProviderRepository()


def handle_greet(state: ConversationState, user_input: str) -> str:
    """Handle greeting state - just transition to check patient."""
    state.current_state = State.CHECK_PATIENT
    return generate_response(state, user_input)


def handle_check_patient(state: ConversationState, user_input: str) -> str:
    """Check if patient exists in database."""
    # Extract any identifying info
    extracted = extract_slots(user_input)
    state.merge_slots(extracted.model_dump(exclude_none=True))

    # Try to find existing patient
    patient = repo.find_existing_patient(
        phone=state.slots.get("phone"),
        email=state.slots.get("email"),
        first_name=state.slots.get("first_name"),
        last_name=state.slots.get("last_name"),
        date_of_birth=state.slots.get("date_of_birth"),
    )

    if patient:
        return _set_returning_patient(state, patient, user_input)

    # No exact match - check if name matches exist (need DOB verification)
    first_name = state.slots.get("first_name")
    last_name = state.slots.get("last_name")
    if first_name and last_name and not state.slots.get("date_of_birth"):
        name_matches = repo.find_patients_by_name(first_name, last_name)
        if name_matches:
            state.pending_name_matches = name_matches
            state.current_state = State.VERIFY_DOB
            return generate_llm_response(
                state, user_input,
                task=f"Found {len(name_matches)} patient(s) named {first_name} {last_name}. Ask for their date of birth to verify identity.",
            )

    # New patient - check what we already have
    intent = classify_intent(user_input)
    if intent.is_negative or "no" in user_input.lower().split():
        # They haven't been here before
        state.current_state = State.COLLECT_PATIENT
        return generate_response(state, user_input)
    elif state.slots.get("phone") or state.slots.get("first_name"):
        # They provided info but we didn't find them
        state.current_state = State.COLLECT_PATIENT
        return generate_llm_response(
            state, user_input,
            task="Patient not found in system. Let them know and start collecting their registration info (name, DOB, phone).",
        )
    else:
        # Ask for identifying info
        return generate_response(state, user_input)


def _set_returning_patient(state: ConversationState, patient, user_input: str) -> str:
    """Set up state for a returning patient."""
    state.is_returning = True
    state.patient_id = patient.id
    state.slots.update({
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "date_of_birth": patient.date_of_birth,
        "phone": patient.phone,
        "email": patient.email,
        "address_line1": patient.address_line1,
        "address_line2": patient.address_line2,
        "city": patient.city,
        "state": patient.state,
        "zip_code": patient.zip_code,
        "address_validated": patient.address_validated,
        "insurance_payer": patient.insurance_payer,
        "insurance_plan": patient.insurance_plan,
        "insurance_member_id": patient.insurance_member_id,
        "insurance_group_id": patient.insurance_group_id,
    })
    state.current_state = State.CONFIRM_RETURNING
    patient_summary = repo.get_patient_summary(patient.id)
    return generate_response(state, user_input, patient_summary=patient_summary)


def handle_verify_dob(state: ConversationState, user_input: str) -> str:
    """Verify patient identity by DOB when name matches exist."""
    extracted = extract_slots(user_input)
    state.merge_slots(extracted.model_dump(exclude_none=True))

    dob = state.slots.get("date_of_birth")
    if not dob:
        return generate_llm_response(
            state, user_input,
            task="Ask for date of birth to verify identity.",
        )

    # Check if DOB matches any of the pending name matches
    for patient in state.pending_name_matches:
        if patient.date_of_birth == dob:
            state.pending_name_matches = []
            return _set_returning_patient(state, patient, user_input)

    # No match - treat as new patient
    state.pending_name_matches = []
    state.current_state = State.COLLECT_PATIENT
    return generate_llm_response(
        state, user_input,
        task="DOB didn't match any records. Let them know and start collecting registration info as new patient.",
    )


def handle_confirm_returning(state: ConversationState, user_input: str) -> str:
    """Handle returning patient confirmation.

    Returning patients can update any info by just stating the new values.
    Non-medical updates go to patients table, medical info creates a new visit.
    """
    intent = classify_intent(user_input)

    # First, try to extract any updates from their message
    extracted = extract_slots(user_input)
    newly_filled = state.merge_slots(extracted.model_dump(exclude_none=True))

    # Check if they updated address fields - need to re-validate
    address_fields = {"address_line1", "city", "state", "zip_code"}
    address_changed = bool(address_fields & set(newly_filled))

    if address_changed:
        # Mark address as needing re-validation
        state.slots["address_validated"] = None
        state.address_validation_attempts = 0

    if intent.wants_to_update or intent.is_negative:
        # They want to update something
        if newly_filled:
            # Check if address is complete and changed - validate it
            if address_changed and state.is_phase_complete(State.COLLECT_ADDRESS):
                return do_address_validation(state, newly_filled) + "\n\nAnything else to update?"
            return generate_response(state, user_input, newly_filled=newly_filled) + "\n\nAnything else to update?"
        elif intent.field_to_update:
            # They said what field they want to update but didn't provide the value
            return generate_llm_response(
                state, user_input,
                task=f"Patient wants to update their {intent.field_to_update}. Ask them for the new value.",
            )
        else:
            return generate_llm_response(
                state, user_input,
                task="Ask what they'd like to update - phone, address, insurance, etc.",
            )

    if intent.is_affirmative:
        # They confirmed info is the same - proceed to medical
        state.current_state = State.COLLECT_MEDICAL
        return generate_response(state, user_input)

    # They provided updates without explicitly saying they want to update
    if newly_filled:
        if address_changed and state.is_phase_complete(State.COLLECT_ADDRESS):
            return do_address_validation(state, newly_filled) + "\n\nAnything else to update?"
        return generate_response(state, user_input, newly_filled=newly_filled) + "\n\nAnything else to update, or is everything correct now?"

    # Unclear response - ask for clarification
    return generate_llm_response(
        state, user_input,
        task="Ask if their information is still correct or if they'd like to update anything.",
    )


def handle_collection(state: ConversationState, user_input: str) -> str:
    """Handle slot collection phases."""
    # Extract slots from input
    extracted = extract_slots(user_input)
    newly_filled = state.merge_slots(extracted.model_dump(exclude_none=True))

    # Check if phase is complete
    if state.is_phase_complete(state.current_state):
        next_state = get_next_state(state)
        state.current_state = next_state

        # If we just completed address collection, auto-validate
        if next_state == State.VALIDATE_ADDRESS:
            return do_address_validation(state, newly_filled)

        # If we just completed medical collection, auto-query providers
        if next_state == State.QUERY_PROVIDERS:
            ack = generate_response(state, user_input, newly_filled=newly_filled)
            return ack + "\n\n" + handle_query_providers(state, user_input)

    return generate_response(state, user_input, newly_filled=newly_filled)


def do_address_validation(state: ConversationState, newly_filled: list[str] | None = None) -> str:
    """Perform address validation and return response."""
    state.address_validation_attempts += 1

    result = validate_address(
        address_line1=state.slots["address_line1"],
        city=state.slots["city"],
        state=state.slots["state"],
        zip_code=state.slots["zip_code"],
        address_line2=state.slots.get("address_line2"),
    )

    ack = ""
    if newly_filled:
        if len(newly_filled) <= 3:
            from assort_intake_bot.conversation import FIELD_NAMES
            fields = ", ".join(FIELD_NAMES.get(f, f) for f in newly_filled)
            ack = f"Thanks! I've recorded your {fields}. "
        else:
            ack = "Thanks for all that information! "

    if result.is_valid:
        state.slots["address_validated"] = True
        if result.corrected_components:
            state.slots.update(result.corrected_components)
        state.current_state = State.CONFIRM_ADDRESS
        return ack + "Your address has been verified. " + generate_response(state, "")
    else:
        if state.address_validation_attempts >= 2:
            state.slots["address_validated"] = False
            state.current_state = State.CONFIRM_ADDRESS
            return ack + "I couldn't fully verify that address, but let's continue. " + generate_response(state, "")
        else:
            # Store the suggestion for potential user acceptance
            state.pending_address_suggestion = result.suggested_address

            # Build error message with suggestion if available
            msg = ack + f"The address \"{result.input_address}\" could not be verified."
            if result.suggested_address:
                msg += f"\n\nDid you mean: **{result.suggested_address}**?\n\nReply 'yes' to use this address, or provide the correct address."
            else:
                msg += "\n\nPlease double-check and provide the correct address."

            state.current_state = State.VALIDATE_ADDRESS
            return msg


def parse_suggested_address(suggested: str) -> dict | None:
    """Parse a formatted address string into components.

    Expected format: "123 Street Name, City, ST 12345, USA"
    """
    import re

    # Remove country suffix if present
    suggested = re.sub(r",?\s*(USA|US|United States)$", "", suggested.strip(), flags=re.IGNORECASE)

    # Split by comma
    parts = [p.strip() for p in suggested.split(",")]

    if len(parts) < 3:
        return None

    result = {}

    # First part is street address
    result["address_line1"] = parts[0]

    # Second part is city
    result["city"] = parts[1]

    # Third part should be "ST 12345" format
    state_zip = parts[2].strip()
    match = re.match(r"^([A-Z]{2})\s+(\d{5})(?:-\d{4})?$", state_zip)
    if match:
        result["state"] = match.group(1)
        result["zip_code"] = match.group(2)
    else:
        # Try just state
        if len(state_zip) == 2 and state_zip.isalpha():
            result["state"] = state_zip.upper()

    return result if "state" in result else None


def handle_validate_address(state: ConversationState, user_input: str) -> str:
    """Handle address correction input and re-validate."""
    # Check if user is accepting the suggested address
    intent = classify_intent(user_input)
    if intent.is_affirmative or "yes" in user_input.lower().split():
        if state.pending_address_suggestion:
            # Accept the suggested address - parse and update slots
            suggested = state.pending_address_suggestion
            # Try to parse the suggested address into components
            # Format is typically: "123 Street, City, ST ZIP, USA"
            parsed = parse_suggested_address(suggested)
            if parsed:
                state.slots.update(parsed)
            state.slots["address_validated"] = True
            state.pending_address_suggestion = None
            state.current_state = State.CONFIRM_ADDRESS
            return generate_llm_response(
                state, user_input,
                task=f"Confirm you've updated their address to: {suggested}. Ask if this is correct.",
                data_to_present={"updated_address": suggested},
            )

    # User is providing corrected address - extract and validate
    extracted = extract_slots(user_input)
    newly_filled = state.merge_slots(extracted.model_dump(exclude_none=True))

    # Clear pending suggestion since user is providing new info
    state.pending_address_suggestion = None

    # Check if we have all address fields
    if state.is_phase_complete(State.COLLECT_ADDRESS):
        return do_address_validation(state, newly_filled)

    return generate_response(state, user_input, newly_filled=newly_filled)


def advance_to_next_actionable_state(state: ConversationState, user_input: str) -> str:
    """Advance through completed phases until we find one needing user input."""
    while True:
        current = state.current_state

        # Collection phases - check if already complete, skip to confirmation
        if current == State.COLLECT_PATIENT:
            if state.is_phase_complete(current):
                state.current_state = State.CONFIRM_PATIENT
                return generate_response(state, user_input)
            return generate_response(state, user_input)

        if current == State.COLLECT_INSURANCE:
            if state.is_phase_complete(current):
                state.current_state = State.CONFIRM_INSURANCE
                return generate_response(state, user_input)
            return generate_response(state, user_input)

        if current == State.COLLECT_ADDRESS:
            if state.is_phase_complete(current):
                state.current_state = State.VALIDATE_ADDRESS
                return do_address_validation(state, [])
            return generate_response(state, user_input)

        # Medical collection - if complete, query providers
        if current == State.COLLECT_MEDICAL:
            if state.is_phase_complete(current):
                state.current_state = State.QUERY_PROVIDERS
                return handle_query_providers(state, user_input)
            return generate_response(state, user_input)

        # For all other states, just generate response
        return generate_response(state, user_input)


def handle_phase_confirm(state: ConversationState, user_input: str, phase: State, next_state: State) -> str:
    """Handle confirmation for a collection phase."""
    intent = classify_intent(user_input)

    if intent.is_affirmative or "yes" in user_input.lower().split():
        state.current_state = next_state
        return advance_to_next_actionable_state(state, user_input)
    elif intent.is_negative or intent.wants_to_update:
        # They want to correct something - extract and update
        extracted = extract_slots(user_input)
        newly_filled = state.merge_slots(extracted.model_dump(exclude_none=True))
        if newly_filled:
            return generate_response(state, user_input, newly_filled=newly_filled) + "\n\nIs this correct now?"
        return generate_llm_response(
            state, user_input,
            task="Ask what they'd like to correct.",
        )
    else:
        # Check for corrections in their response
        extracted = extract_slots(user_input)
        newly_filled = state.merge_slots(extracted.model_dump(exclude_none=True))
        if newly_filled:
            return generate_response(state, user_input, newly_filled=newly_filled) + "\n\nIs this correct now?"
        return generate_llm_response(
            state, user_input,
            task="Ask them to confirm if the information is correct or what needs to be changed.",
        )


def handle_confirm_patient(state: ConversationState, user_input: str) -> str:
    """Handle patient info confirmation."""
    return handle_phase_confirm(state, user_input, State.CONFIRM_PATIENT, State.COLLECT_INSURANCE)


def handle_confirm_insurance(state: ConversationState, user_input: str) -> str:
    """Handle insurance info confirmation."""
    return handle_phase_confirm(state, user_input, State.CONFIRM_INSURANCE, State.COLLECT_ADDRESS)


def handle_confirm_address(state: ConversationState, user_input: str) -> str:
    """Handle address confirmation."""
    return handle_phase_confirm(state, user_input, State.CONFIRM_ADDRESS, State.COLLECT_MEDICAL)


def handle_confirm(state: ConversationState, user_input: str) -> str:
    """Handle final confirmation."""
    intent = classify_intent(user_input)

    # Build appointment data for responses
    appointment_data = {
        "appointment": {
            "provider": state.selected_provider_name,
            "date": state.selected_date,
            "time": state.selected_time,
            "reason": state.slots.get('chief_complaint'),
        },
        "patient": {
            "name": f"{state.slots.get('first_name')} {state.slots.get('last_name')}",
            "dob": state.slots.get('date_of_birth'),
            "phone": state.slots.get('phone'),
        },
        "insurance": {
            "provider": state.slots.get('insurance_payer'),
            "member_id": state.slots.get('insurance_member_id'),
        },
    }

    if intent.is_affirmative or "yes" in user_input.lower().split():
        # Save to database
        save_patient_data(state)
        state.current_state = State.END
        return generate_end_message()
    elif intent.is_negative:
        return generate_llm_response(
            state, user_input,
            task="Ask what they'd like to correct before booking.",
            data_to_present=appointment_data,
        )
    else:
        # Check for corrections
        extracted = extract_slots(user_input)
        newly_filled = state.merge_slots(extracted.model_dump(exclude_none=True))
        if newly_filled:
            return generate_llm_response(
                state, user_input,
                task="Show updated info and ask them to confirm everything is correct to book.",
                data_to_present=appointment_data,
            )
        return generate_llm_response(
            state, user_input,
            task="Show the final appointment summary and ask them to confirm everything is correct to book it.",
            data_to_present=appointment_data,
        )


def save_patient_data(state: ConversationState) -> None:
    """Save or update patient data in the database."""
    slots = state.slots

    if state.is_returning and state.patient_id:
        # Update existing patient
        updates = {k: v for k, v in slots.items() if v is not None and k not in ("chief_complaint", "symptoms", "symptom_duration", "severity")}
        repo.update(state.patient_id, updates, changed_by="chatbot")
        patient_id = state.patient_id
    else:
        # Create new patient
        patient = Patient(
            id=str(uuid.uuid4()),
            first_name=slots["first_name"],
            last_name=slots["last_name"],
            date_of_birth=slots["date_of_birth"],
            phone=slots["phone"],
            email=slots.get("email"),
            address_line1=slots.get("address_line1"),
            address_line2=slots.get("address_line2"),
            city=slots.get("city"),
            state=slots.get("state"),
            zip_code=slots.get("zip_code"),
            address_validated=slots.get("address_validated", False),
            insurance_payer=slots.get("insurance_payer"),
            insurance_plan=slots.get("insurance_plan"),
            insurance_member_id=slots.get("insurance_member_id"),
            insurance_group_id=slots.get("insurance_group_id"),
        )
        patient = repo.create(patient, changed_by="chatbot")
        patient_id = patient.id

    # Create visit record
    visit_id = None
    if slots.get("chief_complaint"):
        visit = repo.create_visit(
            patient_id=patient_id,
            chief_complaint=slots["chief_complaint"],
            symptoms=slots.get("symptoms"),
            symptom_duration=slots.get("symptom_duration"),
            severity=slots.get("severity"),
        )
        visit_id = visit.id

    # Book appointment if selected
    if state.selected_appointment_id:
        provider_repo.book_appointment(
            appointment_id=state.selected_appointment_id,
            patient_id=patient_id,
            visit_id=visit_id,
            reason=slots.get("chief_complaint"),
        )


def handle_query_providers(state: ConversationState, user_input: str) -> str:
    """Query providers based on patient's insurance and complaint."""
    # Find providers that accept patient's insurance and can treat their condition
    providers = provider_repo.find_providers(
        insurance=state.slots.get("insurance_payer"),
        condition=state.slots.get("chief_complaint"),
        limit=5,
    )

    if not providers:
        # Fall back to just insurance match
        providers = provider_repo.find_providers(
            insurance=state.slots.get("insurance_payer"),
            limit=5,
        )

    if not providers:
        # Fall back to all providers
        providers = provider_repo.find_providers(limit=5)

    if providers:
        state.matched_providers = [
            {"id": p.id, "name": p.name, "specialty": p.specialty, "rating": p.rating}
            for p in providers
        ]
        state.current_state = State.SELECT_PROVIDER
        return generate_response(state, user_input)
    else:
        # No providers available - skip to confirmation
        state.current_state = State.CONFIRM
        return generate_llm_response(
            state, user_input,
            task="No providers available at this time. Apologize and let them know we'll contact them when slots open up.",
        )


def handle_select_provider(state: ConversationState, user_input: str) -> str:
    """Handle provider selection from the list using LLM interpretation."""
    # Use LLM to interpret which provider the user selected
    selected_idx = interpret_selection(
        user_input,
        state.matched_providers,
        option_type="provider"
    )

    if selected_idx is not None and 0 <= selected_idx < len(state.matched_providers):
        provider = state.matched_providers[selected_idx]
        state.selected_provider_id = provider["id"]
        state.selected_provider_name = provider["name"]

        # Get available slots for this provider
        slots = provider_repo.get_available_slots(provider["id"], limit=10)
        state.available_slots = [
            {"id": s.id, "date": s.date, "time": s.time}
            for s in slots
        ]

        if state.available_slots:
            state.current_state = State.SELECT_TIME
            return generate_response(state, user_input)
        else:
            # No slots available - ask to pick another provider
            return generate_llm_response(
                state, user_input,
                task=f"{provider['name']} has no available appointments. Apologize and ask them to select another provider from the list.",
                data_to_present={"available_providers": [
                    {"name": p["name"], "specialty": p.get("specialty"), "rating": p.get("rating")}
                    for p in state.matched_providers
                ]},
            )

    # Invalid selection - couldn't interpret
    return generate_llm_response(
        state, user_input,
        task="Couldn't understand which provider they want. Ask them to pick one from the list by number or name.",
        data_to_present={"available_providers": [
            {"name": p["name"], "specialty": p.get("specialty"), "rating": p.get("rating")}
            for p in state.matched_providers
        ]},
    )


def handle_select_time(state: ConversationState, user_input: str) -> str:
    """Handle time slot selection using LLM interpretation."""
    # Use LLM to interpret which time slot the user selected
    selected_idx = interpret_selection(
        user_input,
        state.available_slots,
        option_type="time"
    )

    if selected_idx is not None and 0 <= selected_idx < len(state.available_slots):
        slot = state.available_slots[selected_idx]
        state.selected_appointment_id = slot["id"]
        state.selected_date = slot["date"]
        state.selected_time = slot["time"]
        state.current_state = State.CONFIRM

        # Show confirmation with full appointment details
        appointment_data = {
            "appointment": {
                "provider": state.selected_provider_name,
                "date": state.selected_date,
                "time": state.selected_time,
                "reason": state.slots.get('chief_complaint'),
            },
            "patient": {
                "name": f"{state.slots.get('first_name')} {state.slots.get('last_name')}",
                "dob": state.slots.get('date_of_birth'),
                "phone": state.slots.get('phone'),
            },
            "insurance": {
                "provider": state.slots.get('insurance_payer'),
                "member_id": state.slots.get('insurance_member_id'),
            },
        }
        return generate_llm_response(
            state, user_input,
            task="Show the final appointment summary and ask them to confirm everything is correct to book it.",
            data_to_present=appointment_data,
        )

    # Invalid selection - couldn't interpret
    time_slots = [
        {"option": i+1, "date": s["date"], "time": s["time"]}
        for i, s in enumerate(state.available_slots)
    ]
    return generate_llm_response(
        state, user_input,
        task=f"Couldn't understand which time slot they want. Ask them to pick one from the list.",
        data_to_present={"available_times": time_slots},
    )


# State handlers mapping
STATE_HANDLERS = {
    State.GREET: handle_greet,
    State.CHECK_PATIENT: handle_check_patient,
    State.VERIFY_DOB: handle_verify_dob,
    State.CONFIRM_RETURNING: handle_confirm_returning,
    State.COLLECT_PATIENT: handle_collection,
    State.CONFIRM_PATIENT: handle_confirm_patient,
    State.COLLECT_INSURANCE: handle_collection,
    State.CONFIRM_INSURANCE: handle_confirm_insurance,
    State.COLLECT_ADDRESS: handle_collection,
    State.VALIDATE_ADDRESS: handle_validate_address,
    State.CONFIRM_ADDRESS: handle_confirm_address,
    State.COLLECT_MEDICAL: handle_collection,
    State.QUERY_PROVIDERS: handle_query_providers,
    State.SELECT_PROVIDER: handle_select_provider,
    State.SELECT_TIME: handle_select_time,
    State.CONFIRM: handle_confirm,
}


def process_input(state: ConversationState, user_input: str) -> str:
    """Process user input and return response."""
    handler = STATE_HANDLERS.get(state.current_state)
    if handler:
        return handler(state, user_input)
    return generate_llm_response(
        state, user_input,
        task="Something went wrong. Apologize and ask if they'd like to start over.",
    )


def main():
    """Main chat loop."""
    init_database()

    console.print("[bold blue]Welcome to Assort Health![/bold blue]")
    console.print("Type 'quit' or 'exit' to end the conversation.\n")

    state = ConversationState()

    # Initial greeting
    greeting = generate_greeting()
    console.print("[bold cyan]Bot:[/bold cyan]", Markdown(greeting), "\n")
    state.current_state = State.CHECK_PATIENT

    import sys
    is_tty = sys.stdin.isatty()

    while state.current_state != State.END:
        try:
            user_input = console.input("[bold green]You:[/bold green] ").strip()
            # Echo input when stdin is piped (not interactive)
            if not is_tty and user_input:
                console.print(f"[dim]{user_input}[/dim]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold blue]Goodbye![/bold blue]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            console.print("[bold blue]Goodbye![/bold blue]")
            break

        try:
            with Status("Thinking...", console=console, spinner="dots"):
                response = process_input(state, user_input)
            console.print("[bold cyan]Bot:[/bold cyan]", Markdown(response), "\n")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}\n")

    if state.current_state == State.END:
        console.print("[bold blue]Session complete.[/bold blue]")


if __name__ == "__main__":
    main()
