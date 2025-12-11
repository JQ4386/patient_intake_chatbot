"""Slot extraction using Pydantic models and OpenAI structured output."""

import os
import json
import re
from pydantic import BaseModel, Field, field_validator
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


class ExtractedSlots(BaseModel):
    """All possible slots the LLM might extract from user input."""

    # Patient info
    first_name: str | None = Field(None, description="Patient's first name")
    last_name: str | None = Field(None, description="Patient's last name")
    date_of_birth: str | None = Field(
        None, description="Date of birth in YYYY-MM-DD format"
    )
    phone: str | None = Field(None, description="Phone number (digits only, 10 digits)")
    email: str | None = Field(None, description="Email address")

    # Address
    address_line1: str | None = Field(None, description="Street address")
    address_line2: str | None = Field(None, description="Apartment, suite, unit, etc.")
    city: str | None = Field(None, description="City name")
    state: str | None = Field(
        None, description="State abbreviation (e.g., CA, NY, TX)"
    )
    zip_code: str | None = Field(None, description="5-digit ZIP code")

    # Insurance
    insurance_payer: str | None = Field(
        None, description="Insurance company name (e.g., Blue Cross, Aetna, Kaiser)"
    )
    insurance_plan: str | None = Field(None, description="Plan type (PPO, HMO, etc.)")
    insurance_member_id: str | None = Field(None, description="Insurance member ID")
    insurance_group_id: str | None = Field(None, description="Insurance group ID")

    # Medical
    chief_complaint: str | None = Field(
        None, description="Primary reason for visit / main health concern"
    )
    symptoms: str | None = Field(
        None, description="Symptoms described by patient (as JSON array string)"
    )
    symptom_duration: str | None = Field(
        None, description="How long symptoms have been present"
    )
    severity: int | None = Field(None, ge=1, le=10, description="Pain/severity 1-10")

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def normalize_dob(cls, v):
        """Convert various date formats to YYYY-MM-DD."""
        if not v:
            return None
        # Already in correct format
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            return v
        # MM/DD/YYYY
        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
        if match:
            m, d, y = match.groups()
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        # MM-DD-YYYY
        match = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", v)
        if match:
            m, d, y = match.groups()
            return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, v):
        """Extract digits only from phone number. Stores whatever is provided."""
        if not v:
            return None
        digits = re.sub(r"\D", "", v)
        if not digits:
            return None
        # Normalize 11-digit numbers starting with 1
        if len(digits) == 11 and digits.startswith("1"):
            return digits[1:]
        # Return whatever digits we have - validation happens at check time
        return digits

    @field_validator("state", mode="before")
    @classmethod
    def normalize_state(cls, v):
        """Normalize state to 2-letter abbreviation."""
        if not v:
            return None
        v = v.strip().upper()
        # Already abbreviated
        if len(v) == 2:
            return v
        # Common state name mappings
        states = {
            "CALIFORNIA": "CA",
            "NEW YORK": "NY",
            "TEXAS": "TX",
            "FLORIDA": "FL",
            "ILLINOIS": "IL",
            "PENNSYLVANIA": "PA",
            "OHIO": "OH",
            "GEORGIA": "GA",
            "NORTH CAROLINA": "NC",
            "MICHIGAN": "MI",
            "NEW JERSEY": "NJ",
            "VIRGINIA": "VA",
            "WASHINGTON": "WA",
            "ARIZONA": "AZ",
            "MASSACHUSETTS": "MA",
            "TENNESSEE": "TN",
            "INDIANA": "IN",
            "MISSOURI": "MO",
            "MARYLAND": "MD",
            "WISCONSIN": "WI",
            "COLORADO": "CO",
            "MINNESOTA": "MN",
            "SOUTH CAROLINA": "SC",
            "ALABAMA": "AL",
            "LOUISIANA": "LA",
            "KENTUCKY": "KY",
            "OREGON": "OR",
            "OKLAHOMA": "OK",
            "CONNECTICUT": "CT",
            "UTAH": "UT",
            "IOWA": "IA",
            "NEVADA": "NV",
            "ARKANSAS": "AR",
            "MISSISSIPPI": "MS",
            "KANSAS": "KS",
            "NEW MEXICO": "NM",
            "NEBRASKA": "NE",
            "WEST VIRGINIA": "WV",
            "IDAHO": "ID",
            "HAWAII": "HI",
            "NEW HAMPSHIRE": "NH",
            "MAINE": "ME",
            "MONTANA": "MT",
            "RHODE ISLAND": "RI",
            "DELAWARE": "DE",
            "SOUTH DAKOTA": "SD",
            "NORTH DAKOTA": "ND",
            "ALASKA": "AK",
            "VERMONT": "VT",
            "WYOMING": "WY",
        }
        return states.get(v, v)


class UserIntent(BaseModel):
    """Classify user's intent in the conversation."""

    is_affirmative: bool = Field(
        False, description="User is confirming/agreeing (yes, correct, that's right)"
    )
    is_negative: bool = Field(
        False, description="User is denying/correcting (no, that's wrong)"
    )
    wants_to_update: bool = Field(
        False, description="User wants to update/change their information"
    )
    field_to_update: str | None = Field(
        None, description="Which field the user wants to update (phone, email, address, insurance, etc.)"
    )
    is_greeting: bool = Field(False, description="User is greeting the bot")
    extracted_slots: ExtractedSlots = Field(
        default_factory=ExtractedSlots, description="Any patient info mentioned"
    )


EXTRACTION_PROMPT = """You are a medical intake assistant extracting patient information from conversation.

Extract any patient information mentioned in the user's message. Only extract fields that are explicitly stated.

IMPORTANT GUIDELINES:
- Extract what the user provides, even if incomplete or in non-standard format
- For phone numbers: Extract any digits provided, even if less than 10 digits. The system will validate later.
- For dates: Convert to YYYY-MM-DD format. Handle formats like "10/10/2000", "October 10, 2000", etc.
- For names: Extract first and last names separately if provided together (e.g., "Sarah Smith" → first_name: "Sarah", last_name: "Smith")
- If information seems incomplete but was clearly intended (e.g., "510-5555" for phone), still extract it.

Return a JSON object with EXACTLY these field names (use null for missing/unclear fields):
{
  "first_name": "patient's first/given name",
  "last_name": "patient's last/family name",
  "date_of_birth": "YYYY-MM-DD format",
  "phone": "phone digits (extract whatever is provided)",
  "email": "email address",
  "address_line1": "street address",
  "address_line2": "apartment/suite if any",
  "city": "city name",
  "state": "2-letter state abbreviation",
  "zip_code": "5-digit ZIP",
  "insurance_payer": "insurance company name",
  "insurance_plan": "plan type like PPO, HMO",
  "insurance_member_id": "member ID",
  "insurance_group_id": "group ID",
  "chief_complaint": "reason for visit",
  "symptoms": "symptoms as JSON array string",
  "symptom_duration": "how long symptoms lasted",
  "severity": "1-10 pain/severity scale"
}"""


def extract_slots(user_input: str, context: str = "") -> ExtractedSlots:
    """Extract patient information from user input using LLM."""
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
    ]

    if context:
        messages.append({"role": "assistant", "content": context})

    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(response.choices[0].message.content)
        return ExtractedSlots(**data)
    except (json.JSONDecodeError, Exception):
        return ExtractedSlots()


def classify_intent(user_input: str, context: str = "") -> UserIntent:
    """Classify user intent and extract any slots mentioned."""
    prompt = """Analyze the user's message and determine their intent.

Return a JSON object with EXACTLY these fields:
{
  "is_affirmative": true/false - user is confirming/agreeing (yes, correct, right, sure, ok, yeah),
  "is_negative": true/false - user is denying/correcting (no, that's wrong, incorrect, nope),
  "wants_to_update": true/false - user wants to change/update their information,
  "field_to_update": null or string - if wants_to_update is true, which field do they want to update? Use one of: "phone", "email", "address", "insurance", "name", "date_of_birth", or null if unclear,
  "is_greeting": true/false - user is greeting (hello, hi, hey)
}"""

    messages = [
        {"role": "system", "content": prompt},
    ]

    if context:
        messages.append({"role": "assistant", "content": context})

    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
    )

    try:
        data = json.loads(response.choices[0].message.content)
        # Only keep the intent fields, ignore any extra fields
        intent_data = {
            "is_affirmative": data.get("is_affirmative", False),
            "is_negative": data.get("is_negative", False),
            "wants_to_update": data.get("wants_to_update", False),
            "field_to_update": data.get("field_to_update"),
            "is_greeting": data.get("is_greeting", False),
        }
        return UserIntent(**intent_data)
    except (json.JSONDecodeError, Exception):
        return UserIntent()
