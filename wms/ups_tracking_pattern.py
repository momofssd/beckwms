"""USPS tracking number validation and extraction utilities."""

import re

# USPS tracking number extraction patterns
TRACKING_REGEX = re.compile(r"((?:92|93|94|95)\d{20})")
TRACKING_SPACED_REGEX = re.compile(r"[\d\s-]{20,40}")


def _is_valid_usps_tracking(number: str) -> bool:
    """Validate USPS tracking number format."""
    if not number or len(number) != 22:
        return False
    
    # Must start with valid USPS channel prefix (92, 93, 94, 95)
    if not number.startswith(('92', '93', '94', '95')):
        return False
    
    return True


def _extract_tracking_numbers_from_text(text: str) -> list[str]:
    """Extract valid USPS tracking numbers from text (rightmost valid match)."""
    if not text:
        return []

    numbers = []
    
    # Find all possible 22-digit sequences starting with 92-95
    # Store all candidates with their positions
    candidates = []
    for i in range(len(text) - 21):
        # Check if we're at the start of a valid USPS prefix
        if text[i:i+2] in ('92', '93', '94', '95'):
            # Extract the next 22 characters
            potential = text[i:i+22]
            # Check if all characters are digits
            if potential.isdigit() and len(potential) == 22:
                # Verify it's a valid tracking number
                if _is_valid_usps_tracking(potential):
                    candidates.append((i, potential))
    
    # Take the rightmost (last) valid match for each unique tracking number
    if candidates:
        # Get the last candidate (rightmost position)
        _, tracking = candidates[-1]
        if tracking not in numbers:
            numbers.append(tracking)

    # Also try regex patterns for spaced/hyphenated formats
    for chunk in TRACKING_SPACED_REGEX.findall(text):
        compact = re.sub(r"\D", "", chunk)
        if len(compact) == 22 and compact.startswith(('92', '93', '94', '95')):
            if _is_valid_usps_tracking(compact) and compact not in numbers:
                numbers.append(compact)

    return numbers
