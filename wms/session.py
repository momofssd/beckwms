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
        "last_msg": (None, None),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
