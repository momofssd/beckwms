"""Timezone utilities for converting UTC timestamps to US Central Time."""

from datetime import datetime
from zoneinfo import ZoneInfo


def utc_to_central(dt):
    """Convert UTC timestamp to US Central Time.
    
    Args:
        dt: datetime object (naive or UTC-aware)
        
    Returns:
        datetime object in US Central Time
    """
    if dt is None:
        return None
    
    # If datetime is naive (no timezone info), assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    
    # Convert to US Central Time
    central_dt = dt.astimezone(ZoneInfo("America/Chicago"))
    
    # Return as naive datetime (without timezone info) for display
    return central_dt.replace(tzinfo=None)


def now_central():
    """Get current time in US Central Time.
    
    Returns:
        datetime object in US Central Time
    """
    return datetime.now(ZoneInfo("America/Chicago"))

