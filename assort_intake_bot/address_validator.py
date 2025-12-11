"""Google Maps Address Validation integration."""

import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

API_KEY = os.getenv("MAP_API_KEY")
API_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"


class AddressValidationError(Exception):
    """Raised when address validation fails."""
    pass


def validate_address_raw(address: str) -> dict:
    """
    Validate an address using Google Address Validation API.

    Returns a dict with:
        - is_valid: bool
        - formatted_address: str or None
        - verdict: str (ACCEPT, FIX, CONFIRM, etc.)
        - issues: list of issues found
        - raw_response: full API response
    """
    if not address or not address.strip():
        raise AddressValidationError("Address cannot be empty")

    if not API_KEY:
        raise AddressValidationError("MAP_API_KEY environment variable not set")

    payload = {"address": {"addressLines": [address.strip()]}}

    try:
        response = requests.post(API_URL, json=payload, params={"key": API_KEY}, timeout=10)
    except requests.exceptions.Timeout:
        raise AddressValidationError("API request timed out")
    except requests.exceptions.ConnectionError:
        raise AddressValidationError("Failed to connect to API")

    if response.status_code == 400:
        raise AddressValidationError("Invalid request format")
    elif response.status_code == 403:
        raise AddressValidationError("API key invalid or Address Validation API not enabled")
    elif response.status_code != 200:
        raise AddressValidationError(f"API error: {response.status_code}")

    data = response.json()

    if "result" not in data:
        raise AddressValidationError("Unexpected API response format")

    result = data["result"]
    verdict = result.get("verdict", {})
    address_info = result.get("address", {})

    issues = []
    if not verdict.get("addressComplete", False):
        issues.append("Address is incomplete")
    if verdict.get("hasUnconfirmedComponents", False):
        issues.append("Some address components could not be confirmed")
    if verdict.get("hasReplacedComponents", False):
        issues.append("Some address components were corrected")

    return {
        "is_valid": verdict.get("possibleNextAction") == "ACCEPT",
        "formatted_address": address_info.get("formattedAddress"),
        "verdict": verdict.get("possibleNextAction", "UNKNOWN"),
        "issues": issues,
        "raw_response": data,
    }


class AddressValidationResult:
    """Result of address validation with suggestion."""

    def __init__(
        self,
        is_valid: bool,
        input_address: str,
        suggested_address: str | None = None,
        corrected_components: dict | None = None,
    ):
        self.is_valid = is_valid
        self.input_address = input_address
        self.suggested_address = suggested_address
        self.corrected_components = corrected_components


def validate_address(
    address_line1: str,
    city: str,
    state: str,
    zip_code: str,
    address_line2: str | None = None,
) -> AddressValidationResult:
    """
    Validate an address using Google Address Validation API.

    Args:
        address_line1: Street address
        city: City name
        state: State abbreviation
        zip_code: ZIP code
        address_line2: Optional apartment/suite

    Returns:
        AddressValidationResult with is_valid, input_address, suggested_address, and corrected_components
    """
    # Build address string
    address_parts = [address_line1]
    if address_line2:
        address_parts.append(address_line2)
    address_parts.append(f"{city}, {state} {zip_code}")
    full_address = ", ".join(address_parts)

    try:
        result = validate_address_raw(full_address)

        is_valid = result["is_valid"]
        suggested = result.get("formatted_address")

        # Extract corrected components if available
        corrected = None
        if suggested:
            corrected = {
                "address_line1": address_line1,
                "city": city,
                "state": state,
                "zip_code": zip_code,
            }

        return AddressValidationResult(
            is_valid=is_valid,
            input_address=full_address,
            suggested_address=suggested,
            corrected_components=corrected,
        )

    except AddressValidationError:
        # On validation error, return invalid with no suggestion
        return AddressValidationResult(
            is_valid=False,
            input_address=full_address,
            suggested_address=None,
            corrected_components=None,
        )


def format_address_for_display(
    address_line1: str,
    city: str,
    state: str,
    zip_code: str,
    address_line2: str | None = None,
) -> str:
    """Format address components into a display string."""
    parts = [address_line1]
    if address_line2:
        parts.append(address_line2)
    parts.append(f"{city}, {state} {zip_code}")
    return "\n".join(parts)
