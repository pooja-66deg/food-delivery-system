"""Phone number normalization, shared by every domain that stores a number.

One rule, applied wherever a number reaches the API — registration, profile
edits, restaurant contact details: numbers are stored in E.164 form
(``+<country code><national number>``). A number typed without a country code
is assumed to be Indian and gets ``+91`` prepended, so ``9876543210``,
``098765 43210`` and ``+91-98765-43210`` all resolve to one account instead of
three.

Normalizing here — at the schema boundary, before anything reads the value —
is what makes lookups honest: the ``User.phone`` uniqueness constraint keys off
the canonical form, so one person cannot register twice by typing their number
two ways.
"""

import re

DEFAULT_COUNTRY_CODE = "91"  # India

# Punctuation people type inside numbers; none of it is meaningful.
_SEPARATORS = re.compile(r"[\s()\-./]")
_DIGITS = re.compile(r"\d+")

# number in real use; both bounds count digits only, country code included.
_MIN_DIGITS = 8
_MAX_DIGITS = 15

_NATIONAL_DIGITS = 10  # Indian mobile numbers, sans country code

ERROR_MESSAGE = (
    "must be a valid phone number — 10 digits for India, or "
    "+<country code> followed by the national number"
)


def normalize_phone(value: str) -> str:
    """Return ``value`` in E.164 form, e.g. ``+919876543210``.

    Raises ValueError with a user-facing message if it is not a usable number.
    """
    compact = _SEPARATORS.sub("", value.strip())

    # "00" is the international dialling prefix across most of the world.
    if compact.startswith("00"):
        compact = "+" + compact[2:]

    if compact.startswith("+"):
        digits = compact[1:]
        if not _DIGITS.fullmatch(digits) or not _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
            raise ValueError(ERROR_MESSAGE)
        return "+" + digits

    if not _DIGITS.fullmatch(compact):
        raise ValueError(ERROR_MESSAGE)

    # A national number may carry a trunk prefix — "0" in India — which is
    # dropped once the country code is explicit.
    national = compact.lstrip("0")

    # Already country-coded but missing the "+", e.g. "919876543210".
    if (
        national.startswith(DEFAULT_COUNTRY_CODE)
        and len(national) == len(DEFAULT_COUNTRY_CODE) + _NATIONAL_DIGITS
    ):
        return "+" + national

    if len(national) != _NATIONAL_DIGITS:
        raise ValueError(ERROR_MESSAGE)
    return "+" + DEFAULT_COUNTRY_CODE + national


def normalize_optional_phone(value: str | None) -> str | None:
    """``normalize_phone`` for fields that may be omitted (PATCH payloads)."""
    return None if value is None else normalize_phone(value)
