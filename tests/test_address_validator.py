"""Test Google Maps Address Validation API."""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("MAP_API_KEY")
API_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"


class AddressValidationError(Exception):
    """Raised when address validation fails."""
    pass


def validate_address(address: str) -> dict:
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


# === Valid Address Tests ===

def test_valid_complete_address():
    """Test a well-known valid address."""
    result = validate_address("1600 Amphitheatre Parkway, Mountain View, CA 94043")
    assert result["is_valid"] is True
    assert result["formatted_address"] is not None
    assert "Mountain View" in result["formatted_address"]
    assert result["verdict"] == "ACCEPT"


def test_valid_address_without_zip():
    """Test a valid address missing zip code (should still validate)."""
    result = validate_address("350 5th Avenue, New York, NY")
    assert result["is_valid"] is True
    assert result["formatted_address"] is not None


def test_valid_address_with_typo():
    """Test address with minor typo gets corrected."""
    result = validate_address("1600 Amphitheatre Pkwy, Montain View, CA")  # "Montain" typo
    assert result["formatted_address"] is not None
    assert "Mountain View" in result["formatted_address"]


def test_valid_address_lowercase():
    """Test lowercase address gets normalized."""
    result = validate_address("1600 amphitheatre parkway, mountain view, ca")
    assert result["formatted_address"] is not None


def test_valid_address_with_extra_whitespace():
    """Test address with extra whitespace."""
    result = validate_address("  1600 Amphitheatre Parkway,   Mountain View,  CA  ")
    assert result["formatted_address"] is not None


# === Invalid/Edge Case Address Tests ===

def test_incomplete_address():
    """Test an incomplete address."""
    result = validate_address("123 Main St")
    # May or may not be valid depending on API interpretation
    # But should not raise an exception
    assert "is_valid" in result


def test_nonexistent_address():
    """Test an address that doesn't exist."""
    result = validate_address("99999 Nonexistent Street, Fakeville, ZZ 00000")
    # API should return something, even if not valid
    assert "is_valid" in result


def test_po_box_address():
    """Test PO Box address."""
    result = validate_address("PO Box 12345, Los Angeles, CA 90001")
    assert "is_valid" in result


def test_apartment_address():
    """Test address with apartment number."""
    result = validate_address("100 Main St, Apt 5B, New York, NY 10001")
    assert "is_valid" in result


def test_international_address():
    """Test non-US address."""
    result = validate_address("10 Downing Street, London, UK")
    assert "is_valid" in result


# === Error Handling Tests ===

def test_empty_address_raises_error():
    """Test that empty address raises error."""
    with pytest.raises(AddressValidationError, match="Address cannot be empty"):
        validate_address("")


def test_whitespace_only_raises_error():
    """Test that whitespace-only address raises error."""
    with pytest.raises(AddressValidationError, match="Address cannot be empty"):
        validate_address("   ")


def test_none_address_raises_error():
    """Test that None address raises error."""
    with pytest.raises(AddressValidationError):
        validate_address(None)


# === Fuzz Testing ===

def test_special_characters():
    """Test address with special characters."""
    result = validate_address("123 O'Connor St, San Francisco, CA")
    assert "is_valid" in result


def test_unicode_characters():
    """Test address with unicode characters."""
    result = validate_address("123 Café Street, San José, CA")
    assert "is_valid" in result


def test_very_long_address():
    """Test very long address string is rejected by API."""
    long_address = "123 " + "A" * 500 + " Street, City, ST 12345"
    with pytest.raises(AddressValidationError, match="Invalid request format"):
        validate_address(long_address)


def test_numeric_only_address():
    """Test numeric-only input."""
    result = validate_address("12345")
    assert "is_valid" in result


def test_address_with_newlines():
    """Test address with newline characters."""
    result = validate_address("123 Main St\nApt 5\nNew York, NY")
    assert "is_valid" in result


def test_address_with_html():
    """Test address with HTML-like content (should be treated as text)."""
    result = validate_address("<script>123</script> Main St, City, ST")
    assert "is_valid" in result


# === Response Structure Tests ===

def test_response_has_required_fields():
    """Test that response contains all expected fields."""
    result = validate_address("1600 Amphitheatre Parkway, Mountain View, CA")
    assert "is_valid" in result
    assert "formatted_address" in result
    assert "verdict" in result
    assert "issues" in result
    assert "raw_response" in result


def test_raw_response_structure():
    """Test that raw response has expected Google API structure."""
    result = validate_address("1600 Amphitheatre Parkway, Mountain View, CA")
    raw = result["raw_response"]
    assert "result" in raw
    assert "verdict" in raw["result"]
    assert "address" in raw["result"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
