"""Conversation management and response generation."""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from assort_intake_bot.state_machine import State, ConversationState, PHASE_REQUIREMENTS

load_dotenv(override=True)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


# Field display names for user-friendly messages
FIELD_NAMES = {
    "first_name": "first name",
    "last_name": "last name",
    "date_of_birth": "date of birth",
    "phone": "phone number",
    "email": "email address",
    "address_line1": "street address",
    "address_line2": "apartment/suite",
    "city": "city",
    "state": "state",
    "zip_code": "ZIP code",
    "insurance_payer": "insurance provider",
    "insurance_plan": "insurance plan type",
    "insurance_member_id": "member ID",
    "insurance_group_id": "group ID",
    "chief_complaint": "reason for visit",
    "symptoms": "symptoms",
    "symptom_duration": "symptom duration",
    "severity": "severity (1-10)",
}


def generate_greeting() -> str:
    """Generate the initial greeting message."""
    return (
        "Hi there! Welcome to Assort Health - I'm so glad you reached out today. "
        "My name is Alex, and I'll be helping you get an appointment scheduled.\n\n"
        "Have you visited us before? If so, I can pull up your information to save you some time!"
    )


def generate_check_patient_prompt(state: ConversationState) -> str:
    """Generate prompt to identify the patient."""
    return (
        "No problem! To look you up in our system, could you share your phone number "
        "or your name and date of birth? Either works great!"
    )


def generate_returning_patient_greeting(patient_summary: dict, slots: dict) -> str:
    """Generate greeting for returning patient with their stored info."""
    name = patient_summary.get("name", "")
    recent = patient_summary.get("recent_complaints", [])

    msg = f"Oh wonderful, {name}! So nice to have you back with us. 😊\n\n"

    if recent:
        msg += f"I see your last visit was for {recent[0]} - I hope you're feeling better since then!\n\n"

    msg += "Let me pull up what we have on file for you:\n\n"

    # Contact info
    msg += "**Contact:**\n"
    msg += f"- Phone: {slots.get('phone', 'Not on file')}\n"
    if slots.get("email"):
        msg += f"- Email: {slots['email']}\n"

    # Address
    if slots.get("address_line1"):
        msg += f"- Address: {slots['address_line1']}"
        if slots.get("address_line2"):
            msg += f", {slots['address_line2']}"
        msg += f", {slots.get('city', '')}, {slots.get('state', '')} {slots.get('zip_code', '')}\n"

    # Insurance
    msg += "\n**Insurance:**\n"
    if slots.get("insurance_payer"):
        msg += f"- Provider: {slots['insurance_payer']}"
        if slots.get("insurance_plan"):
            msg += f" ({slots['insurance_plan']})"
        msg += "\n"
        if slots.get("insurance_member_id"):
            msg += f"- Member ID: {slots['insurance_member_id']}\n"
    else:
        msg += "- No insurance on file\n"

    msg += "\nIs this still correct, or would you like to update anything?"
    return msg


def generate_collection_prompt(state: ConversationState) -> str:
    """Generate prompt for the current collection phase."""
    current = state.current_state
    missing = state.get_missing_slots(current)

    if not missing:
        return ""

    if current == State.COLLECT_PATIENT:
        if len(missing) == len(PHASE_REQUIREMENTS[current]):
            return (
                "Let's get you registered. Could you please tell me your "
                "full name, date of birth, and phone number?"
            )
        else:
            fields = ", ".join(FIELD_NAMES.get(f, f) for f in missing)
            return f"I still need your {fields}."

    if current == State.COLLECT_INSURANCE:
        if len(missing) == len(PHASE_REQUIREMENTS[current]):
            return (
                "Now I'll need your insurance information. "
                "Who is your insurance provider, and what is your member ID?"
            )
        else:
            fields = ", ".join(FIELD_NAMES.get(f, f) for f in missing)
            return f"I still need your {fields}."

    if current == State.COLLECT_ADDRESS:
        if len(missing) == len(PHASE_REQUIREMENTS[current]):
            return "What is your home address? Please include street, city, state, and ZIP code."
        else:
            fields = ", ".join(FIELD_NAMES.get(f, f) for f in missing)
            return f"I still need your {fields}."

    if current == State.COLLECT_MEDICAL:
        return "What is the main reason for your visit today?"

    return ""


def generate_address_invalid_message(state: ConversationState) -> str:
    """Generate message when address validation fails."""
    attempts = state.address_validation_attempts
    if attempts == 1:
        return (
            "I couldn't verify that address. Could you please double-check it? "
            "Make sure to include the complete street address, city, state, and ZIP code."
        )
    else:
        return (
            "I'm still having trouble validating that address. "
            "Let me try to proceed with what you provided. "
            "We may need to verify it when you arrive."
        )


def generate_confirm_patient(state: ConversationState) -> str:
    """Generate patient info confirmation message."""
    slots = state.slots
    msg = "Let me confirm your information:\n\n"
    msg += f"**Name:** {slots['first_name']} {slots['last_name']}\n"
    msg += f"**Date of Birth:** {slots['date_of_birth']}\n"
    msg += f"**Phone:** {slots['phone']}\n"
    if slots.get("email"):
        msg += f"**Email:** {slots['email']}\n"
    msg += "\nIs this correct?"
    return msg


def generate_confirm_insurance(state: ConversationState) -> str:
    """Generate insurance info confirmation message."""
    slots = state.slots
    msg = "Here's your insurance information:\n\n"
    msg += f"**Insurance Provider:** {slots['insurance_payer']}\n"
    if slots.get("insurance_plan"):
        msg += f"**Plan Type:** {slots['insurance_plan']}\n"
    msg += f"**Member ID:** {slots['insurance_member_id']}\n"
    if slots.get("insurance_group_id"):
        msg += f"**Group ID:** {slots['insurance_group_id']}\n"
    msg += "\nIs this correct?"
    return msg


def generate_confirm_address(state: ConversationState) -> str:
    """Generate address confirmation message."""
    slots = state.slots
    msg = "Here's your address:\n\n"
    msg += f"**Address:** {slots['address_line1']}"
    if slots.get("address_line2"):
        msg += f", {slots['address_line2']}"
    msg += f"\n{slots['city']}, {slots['state']} {slots['zip_code']}\n"
    if slots.get("address_validated"):
        msg += "*(Address verified)*\n"
    msg += "\nIs this correct?"
    return msg


def generate_confirmation(state: ConversationState) -> str:
    """Generate the final confirmation message."""
    slots = state.slots

    msg = "Great! Here's a summary of your appointment:\n\n"

    # Appointment details (if available)
    if state.selected_provider_name and state.selected_date:
        msg += f"**Appointment with:** {state.selected_provider_name}\n"
        msg += f"**Date/Time:** {state.selected_date} at {state.selected_time}\n"
        msg += f"**Reason:** {slots['chief_complaint']}\n\n"
        msg += "---\n\n"

    msg += "**Your Information:**\n\n"
    msg += f"**Name:** {slots['first_name']} {slots['last_name']}\n"
    msg += f"**Date of Birth:** {slots['date_of_birth']}\n"
    msg += f"**Phone:** {slots['phone']}\n"

    if slots.get("email"):
        msg += f"**Email:** {slots['email']}\n"

    msg += f"\n**Address:** {slots['address_line1']}"
    if slots.get("address_line2"):
        msg += f", {slots['address_line2']}"
    msg += f"\n{slots['city']}, {slots['state']} {slots['zip_code']}\n"

    msg += f"\n**Insurance:** {slots['insurance_payer']}"
    if slots.get("insurance_plan"):
        msg += f" ({slots['insurance_plan']})"
    msg += f"\n**Member ID:** {slots['insurance_member_id']}\n"

    msg += "\nIs everything correct? Say 'yes' to confirm or tell me what needs to be changed."

    return msg


def generate_provider_selection(state: ConversationState) -> str:
    """Generate provider selection prompt."""
    providers = state.matched_providers
    if not providers:
        return "I'm searching for available providers..."

    msg = "Based on your information, here are available providers:\n\n"
    for i, p in enumerate(providers, 1):
        msg += f"**{i}. {p['name']}**"
        if p.get("specialty"):
            msg += f" - {p['specialty']}"
        if p.get("rating"):
            msg += f" (★ {p['rating']:.1f})"
        msg += "\n"

    msg += "\nPlease select a provider by number or name."
    return msg


def generate_time_selection(state: ConversationState) -> str:
    """Generate time slot selection prompt."""
    slots = state.available_slots
    if not slots:
        return "I'm checking available times..."

    provider_name = state.selected_provider_name or "your provider"
    msg = f"Here are the available appointment times with **{provider_name}**:\n\n"

    for i, slot in enumerate(slots, 1):
        msg += f"**{i}.** {slot['date']} at {slot['time']}\n"

    msg += "\nPlease select a time slot by number."
    return msg


def generate_end_message() -> str:
    """Generate the final goodbye message."""
    return (
        "Thank you! Your appointment has been booked. "
        "We look forward to seeing you!\n\n"
        "Take care!"
    )


def generate_warm_acknowledgement(newly_filled: list[str], slots: dict) -> str:
    """Generate a warm, personalized acknowledgement of what the user provided."""
    if not newly_filled:
        return ""

    # Use the patient's name if we have it for a personal touch
    name = slots.get("first_name")

    if len(newly_filled) == 1:
        field = newly_filled[0]
        field_name = FIELD_NAMES.get(field, field)
        value = slots.get(field)

        # Personalized responses based on what was provided
        if field == "first_name" or field == "last_name":
            full_name = f"{slots.get('first_name', '')} {slots.get('last_name', '')}".strip()
            if full_name:
                return f"Nice to meet you, {full_name}! "
            return f"Thanks, {value}! "
        elif field == "date_of_birth":
            return f"Got it, I've noted your date of birth. "
        elif field == "phone":
            return f"Thanks! I've saved your phone number. "
        elif field == "email":
            return f"Great, I've noted your email address. "
        elif field == "chief_complaint":
            return f"I understand you're here for {value}. I'm sorry to hear that. "
        elif field == "insurance_payer":
            return f"Thanks! I see you have {value}. "
        elif field in ("address_line1", "city", "state", "zip_code"):
            return f"Got it, I've recorded your {field_name}. "
        else:
            return f"Thanks, I've noted your {field_name}. "

    elif len(newly_filled) <= 3:
        fields = ", ".join(FIELD_NAMES.get(f, f) for f in newly_filled)
        if name:
            return f"Thanks, {name}! I've recorded your {fields}. "
        return f"Great, I've got your {fields}. "
    else:
        if name:
            return f"Thanks for all that information, {name}! "
        return "Thanks for sharing all that! "


def generate_response(
    state: ConversationState,
    user_input: str,
    newly_filled: list[str] | None = None,
    patient_summary: dict | None = None,
    address_valid: bool | None = None,  # kept for backward compatibility
) -> str:
    """Generate a contextual response based on state and what was just collected.

    Uses LLM to generate natural, human-like responses.
    """
    return generate_dynamic_response(
        state=state,
        user_input=user_input,
        newly_filled=newly_filled,
        patient_summary=patient_summary,
    )


def generate_llm_response(
    state: ConversationState,
    user_input: str,
    task: str,
    data_to_present: dict | None = None,
) -> str:
    """Use LLM to generate a natural, human-like response.

    Args:
        state: Current conversation state
        user_input: What the user just said
        task: What the bot needs to accomplish (e.g., "confirm patient info", "ask for insurance")
        data_to_present: Any structured data to include in the response
    """
    collected = {k: v for k, v in state.slots.items() if v}
    patient_name = state.slots.get("first_name", "")

    system_prompt = f"""You are Alex, a warm and friendly patient intake coordinator at Assort Health.
You're helping patients schedule appointments over chat - be personable, empathetic, and conversational.

PERSONALITY:
- Warm and caring - patients may be anxious or in pain
- Natural and human - use contractions, casual language
- Efficient but not rushed - acknowledge what they say before moving on
- Empathetic - if they mention pain or health issues, show you care

CURRENT TASK: {task}

PATIENT INFO COLLECTED SO FAR:
{json.dumps(collected, indent=2) if collected else "None yet"}

{f"Patient's name: {patient_name}" if patient_name else ""}

DATA TO INCLUDE IN RESPONSE:
{json.dumps(data_to_present, indent=2) if data_to_present else "None"}

RULES:
- Keep responses concise (2-4 sentences max, unless presenting data)
- Always acknowledge what the user just said before asking for more
- When presenting data (like confirmations), format it clearly with markdown
- Sound like a real person, not a script
- Use the patient's first name when you have it
- Don't be overly formal or robotic
- Do NOT use emojis
- IMPORTANT: When DATA TO INCLUDE is provided, you MUST include ALL items from that data in your response. Never omit data items."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input if user_input else "(conversation start)"},
    ]

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_completion_tokens=1024,
    )

    result = response.choices[0].message.content or ""
    if not result.strip():
        # Fallback if LLM returns empty - provide a formatted response
        if data_to_present:
            return _format_data_fallback(data_to_present, task)
        return "I'm sorry, could you please repeat that?"
    return result


def _format_data_fallback(data: dict, task: str) -> str:
    """Format data nicely when LLM returns empty response."""
    lines = []

    # Handle available times
    if "available_times" in data:
        lines.append("Here are the available times:\n")
        for slot in data["available_times"]:
            lines.append(f"- Option {slot['option']}: {slot['date']} at {slot['time']}")
        lines.append("\nPlease pick one by number.")
        return "\n".join(lines)

    # Handle available providers
    if "available_providers" in data:
        lines.append("Here are the available providers:\n")
        for i, p in enumerate(data["available_providers"], 1):
            lines.append(f"- {i}. {p['name']} - {p.get('specialty', 'N/A')} (Rating: {p.get('rating', 'N/A')})")
        lines.append("\nPlease pick one by number or name.")
        return "\n".join(lines)

    # Handle appointment confirmation
    if "appointment" in data:
        appt = data["appointment"]
        patient = data.get("patient", {})
        insurance = data.get("insurance", {})

        lines.append("**Appointment Summary**\n")
        lines.append(f"- Provider: {appt.get('provider')}")
        lines.append(f"- Date: {appt.get('date')}")
        lines.append(f"- Time: {appt.get('time')}")
        lines.append(f"- Reason: {appt.get('reason')}")
        lines.append("\n**Patient**\n")
        lines.append(f"- Name: {patient.get('name')}")
        lines.append(f"- DOB: {patient.get('dob')}")
        lines.append(f"- Phone: {patient.get('phone')}")
        lines.append("\n**Insurance**\n")
        lines.append(f"- Provider: {insurance.get('provider')}")
        lines.append(f"- Member ID: {insurance.get('member_id')}")
        lines.append("\nIs everything correct? Reply 'yes' to confirm booking.")
        return "\n".join(lines)

    # Generic fallback
    return f"Please review:\n\n{json.dumps(data, indent=2)}\n\nIs everything correct?"


def interpret_selection(user_input: str, options: list[dict], option_type: str) -> int | None:
    """Use LLM to interpret which option the user selected.

    Args:
        user_input: What the user said
        options: List of options (each with 'name' or descriptive keys)
        option_type: Type of selection ("provider" or "time")

    Returns:
        The 0-based index of the selected option, or None if unclear
    """
    if not options:
        return None

    # Format options for the LLM
    options_text = ""
    for i, opt in enumerate(options, 1):
        if option_type == "provider":
            options_text += f"{i}. {opt.get('name', '')} - {opt.get('specialty', '')}\n"
        elif option_type == "time":
            options_text += f"{i}. {opt.get('date', '')} at {opt.get('time', '')}\n"
        else:
            options_text += f"{i}. {opt}\n"

    system_prompt = f"""Pick which option (1-{len(options)}) the user selected. Reply with just the number.

OPTIONS:
{options_text}
USER SAID: "{user_input}"

Rules: If they mention a name/number, pick that one. If they say "yes/yep/first one", pick 1. If unclear, say 0."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        max_completion_tokens=512,  # Need enough for reasoning tokens + response
    )

    result = (response.choices[0].message.content or "").strip()

    # Parse the response - extract first number found
    import re
    numbers = re.findall(r'\d+', result)
    if numbers:
        selection = int(numbers[0])
        if 1 <= selection <= len(options):
            return selection - 1  # Convert to 0-based index
        elif selection == 0:
            return None

    return None


def generate_dynamic_response(
    state: ConversationState,
    user_input: str,
    newly_filled: list[str] | None = None,
    patient_summary: dict | None = None,
) -> str:
    """Generate a dynamic, LLM-powered response based on state."""
    current = state.current_state
    slots = state.slots

    # Determine task and data based on state
    if current == State.GREET:
        return generate_llm_response(
            state, user_input,
            task="Greet the patient warmly, introduce yourself as Alex from Assort Health, and ask if they've visited before so you can look up their info.",
        )

    if current == State.CHECK_PATIENT:
        return generate_llm_response(
            state, user_input,
            task="Ask for their phone number or name and date of birth so you can look them up in the system.",
        )

    if current == State.CONFIRM_RETURNING:
        if patient_summary:
            recent_complaints = patient_summary.get("recent_complaints", [])
            data = {
                "name": patient_summary.get("name"),
                "phone": slots.get("phone"),
                "email": slots.get("email"),
                "address": f"{slots.get('address_line1', '')}, {slots.get('city', '')}, {slots.get('state', '')} {slots.get('zip_code', '')}".strip(", "),
                "insurance": slots.get("insurance_payer"),
                "member_id": slots.get("insurance_member_id"),
                "last_visit_reason": recent_complaints[0] if recent_complaints else None,
            }
            return generate_llm_response(
                state, user_input,
                task="Welcome back this returning patient! Show them the info on file and ask if it's still correct or if they need to update anything.",
                data_to_present=data,
            )
        return generate_llm_response(
            state, user_input,
            task="Welcome back and ask if their information is still the same.",
        )

    if current == State.COLLECT_PATIENT:
        missing = state.get_missing_slots(current)
        if newly_filled:
            task = f"Acknowledge what they provided, then ask for the remaining info: {', '.join(FIELD_NAMES.get(f, f) for f in missing)}"
        else:
            task = f"Ask for their basic info: full name, date of birth, and phone number."
        return generate_llm_response(state, user_input, task=task)

    if current == State.CONFIRM_PATIENT:
        data = {
            "name": f"{slots['first_name']} {slots['last_name']}",
            "date_of_birth": slots['date_of_birth'],
            "phone": slots['phone'],
            "email": slots.get('email'),
        }
        return generate_llm_response(
            state, user_input,
            task="Show them their info and ask them to confirm it's correct.",
            data_to_present=data,
        )

    if current == State.COLLECT_INSURANCE:
        missing = state.get_missing_slots(current)
        if newly_filled:
            task = f"Acknowledge what they provided, then ask for: {', '.join(FIELD_NAMES.get(f, f) for f in missing)}"
        else:
            task = "Now ask for their insurance information - provider name and member ID."
        return generate_llm_response(state, user_input, task=task)

    if current == State.CONFIRM_INSURANCE:
        data = {
            "insurance_provider": slots['insurance_payer'],
            "plan_type": slots.get('insurance_plan'),
            "member_id": slots['insurance_member_id'],
            "group_id": slots.get('insurance_group_id'),
        }
        return generate_llm_response(
            state, user_input,
            task="Show them their insurance info and ask them to confirm it's correct.",
            data_to_present=data,
        )

    if current == State.COLLECT_ADDRESS:
        missing = state.get_missing_slots(current)
        if newly_filled:
            task = f"Acknowledge what they provided, then ask for: {', '.join(FIELD_NAMES.get(f, f) for f in missing)}"
        else:
            task = "Ask for their home address - street, city, state, and ZIP code."
        return generate_llm_response(state, user_input, task=task)

    if current == State.CONFIRM_ADDRESS:
        address = f"{slots['address_line1']}"
        if slots.get('address_line2'):
            address += f", {slots['address_line2']}"
        address += f", {slots['city']}, {slots['state']} {slots['zip_code']}"
        data = {
            "address": address,
            "verified": slots.get('address_validated', False),
        }
        return generate_llm_response(
            state, user_input,
            task="Show them their address (mention if it was verified) and ask them to confirm.",
            data_to_present=data,
        )

    if current == State.COLLECT_MEDICAL:
        if newly_filled and 'chief_complaint' in newly_filled:
            return generate_llm_response(
                state, user_input,
                task=f"Acknowledge their reason for visit ({slots.get('chief_complaint')}) with empathy - they may be in discomfort. Let them know you'll find them a great provider.",
            )
        return generate_llm_response(
            state, user_input,
            task="Ask what brings them in today / the main reason for their visit.",
        )

    if current == State.SELECT_PROVIDER:
        providers = state.matched_providers
        provider_list = [
            {"name": p["name"], "specialty": p.get("specialty"), "rating": p.get("rating")}
            for p in providers
        ]
        return generate_llm_response(
            state, user_input,
            task="Present the available providers and ask them to pick one by number or name.",
            data_to_present={"available_providers": provider_list},
        )

    if current == State.SELECT_TIME:
        time_slots = [
            {"option": i+1, "date": s["date"], "time": s["time"]}
            for i, s in enumerate(state.available_slots)
        ]
        return generate_llm_response(
            state, user_input,
            task=f"Show available appointment times with {state.selected_provider_name} and ask them to pick one.",
            data_to_present={"available_times": time_slots},
        )

    if current == State.CONFIRM:
        data = {
            "appointment": {
                "provider": state.selected_provider_name,
                "date": state.selected_date,
                "time": state.selected_time,
                "reason": slots['chief_complaint'],
            },
            "patient": {
                "name": f"{slots['first_name']} {slots['last_name']}",
                "dob": slots['date_of_birth'],
                "phone": slots['phone'],
            },
            "insurance": {
                "provider": slots['insurance_payer'],
                "member_id": slots['insurance_member_id'],
            },
        }
        return generate_llm_response(
            state, user_input,
            task="Show a final summary of the appointment and all their info. Ask them to confirm everything is correct to book it.",
            data_to_present=data,
        )

    if current == State.END:
        return generate_llm_response(
            state, user_input,
            task="Thank them warmly, confirm the appointment is booked, and wish them well. Be genuine and caring.",
        )

    # Fallback
    return generate_llm_response(
        state, user_input,
        task="Continue helping the patient with their intake.",
    )
