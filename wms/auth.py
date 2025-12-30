import hashlib
import streamlit as st


def hash_pass(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def login_ui(users_col) -> None:
    """Render login UI and set session auth state."""
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        st.title("WMS System Login")
        with st.form("login_form"):
            user = st.text_input("Username")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                user_data = users_col.find_one({"username": user, "password": hash_pass(pw)})
                if user_data:
                    st.session_state.authenticated = True
                    st.session_state.user_role = user_data["role"]
                    st.session_state.username = user_data["username"]
                    st.rerun()
                else:
                    st.error("Invalid credentials.")


def require_auth(users_col) -> None:
    if not st.session_state.authenticated:
        login_ui(users_col)
        st.stop()

