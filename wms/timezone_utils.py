"""Timezone utilities for converting UTC timestamps to US Central Time."""

from datetime import datetime
from zoneinfo import ZoneInfo


def utc_to_central(dt):
    """Convert a UTC datetime to US Central Time.
    
    Args:
        dt: datetime object (naive or UTC-aware)
        
    Returns:
        datetime object in US Central Time
    """
    if dt is None:
        return None
    
    try:
        # If datetime is naive, assume it's UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        
        # Convert to US Central Time
        central_tz = ZoneInfo("America/Chicago")
        return dt.astimezone(central_tz)
    except Exception:
        # If conversion fails, return original
        return dt


def now_central():
    """Get current time in US Central Time.
    
    Returns:
        datetime object in US Central Time
    """
    return datetime.now(ZoneInfo("America/Chicago"))
