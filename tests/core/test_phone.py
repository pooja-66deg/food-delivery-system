"""Phone normalization rules shared by every domain."""
import pytest

from src.core.phone import normalize_optional_phone, normalize_phone


@pytest.mark.parametrize("raw,expected", [
    # Bare national numbers pick up the default country code.
    ("9876543210", "+919876543210"),
    ("98765 43210", "+919876543210"),
    ("98765-43210", "+919876543210"),
    ("(98765) 43210", "+919876543210"),
    ("  9876543210  ", "+919876543210"),
    # Trunk prefix is dropped once the country code is explicit.
    ("09876543210", "+919876543210"),
    # Country code already present, in each of the ways people write it.
    ("+919876543210", "+919876543210"),
    ("+91 98765 43210", "+919876543210"),
    ("919876543210", "+919876543210"),
    ("0091 98765 43210", "+919876543210"),
    # Other countries stay untouched — only the punctuation goes.
    ("+1 555 000 0000", "+15550000000"),
    ("+44 20 7946 0958", "+442079460958"),
])
def test_normalizes_to_e164(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "call-me",
    "55512ab345",
    "555 123 4567!",
    "12345",             # too short for a national number
    "987654321",         # 9 digits — one short
    "98765432101",       # 11 digits — one over
    "+1",                # country code with no number
    "+1234567890123456",  # past the E.164 15-digit cap
])
def test_rejects_unusable_numbers(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_optional_passes_none_through():
    assert normalize_optional_phone(None) is None
    assert normalize_optional_phone("9876543210") == "+919876543210"


def test_same_number_written_differently_normalizes_alike():
    """The property the uniqueness constraint and OTP keys depend on."""
    forms = ["9876543210", "098765 43210", "+91-98765-43210", "919876543210"]
    assert len({normalize_phone(f) for f in forms}) == 1
