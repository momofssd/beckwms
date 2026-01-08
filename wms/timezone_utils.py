"""Timezone utilities for converting UTC timestamps to US Central Time."""

from datetime import datetime
from zoneinfo import ZoneInfo


def utc_to_central(dt):
    """Return the exact timestamp from database without timezone conversion.
    
    Args:
        dt: datetime object (naive or UTC-aware)
        
    Returns:
        datetime object as-is without conversion
    """
    if dt is None:
        return None
    
    # Return the timestamp as-is without any timezone conversion
    return dt


def now_central():
    """Get current time in US Central Time.
    
    Returns:
        datetime object in US Central Time
    """
    return datetime.now(ZoneInfo("America/Chicago"))

