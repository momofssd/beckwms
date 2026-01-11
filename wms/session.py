import streamlit as st


def ensure_session_state_initialized() -> None:
    defaults = {
        "authenticated": False,
        "user_role": None,
        "username": None,
        # Default landing page after login
        "page": "home",
        "scan_pair": [],
        "session_log": [],
        # Outbound session workflow
        # - outbound_pending: list of outbound transaction dicts collected during a session
        # - outbound_confirmed: once True, pending has been applied to DB and export is enabled
        # - outbound_session_active: gate UI so user must click New Session first
        "outbound_pending": [],
        "outbound_confirmed": False,
        "outbound_session_active": False,
        "last_msg": (None, None),
        # Default location selection for inbound/outbound/sto
        "default_location": None,
        # Audio settings for SKU scan feedback
        "audio_enabled": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
