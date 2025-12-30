from __future__ import annotations

import streamlit as st

from wms.auth import require_auth
from wms.db import get_collections
from wms.session import ensure_session_state_initialized
from wms.pages import home as home_page
from wms.pages import inbound as inbound_page
from wms.pages import outbound as outbound_page


def render_sidebar() -> None:
    st.sidebar.title(f"Welcome, {st.session_state.username}")
    st.sidebar.caption(
        f"Role: {st.session_state.user_role.upper() if st.session_state.user_role else ''}"
    )
    st.sidebar.divider()

    if st.sidebar.button("Inventory Dashboard", use_container_width=True):
        st.session_state.page = "home"
    if st.sidebar.button("Inbound Entry", use_container_width=True):
        st.session_state.page = "inbound"
    if st.sidebar.button("Outbound Processing", use_container_width=True):
        st.session_state.page = "outbound"

    st.sidebar.divider()
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()


def run() -> None:
    st.set_page_config(page_title="Beck's WMS", layout="wide")

    cols = get_collections()
    inventory_col = cols["inventory"]
    transactions_col = cols["transactions"]
    users_col = cols["users"]

    ensure_session_state_initialized()
    require_auth(users_col)
    render_sidebar()

    if st.session_state.page == "home":
        home_page.render(inventory_col=inventory_col)
    elif st.session_state.page == "outbound":
        outbound_page.render(inventory_col=inventory_col, transactions_col=transactions_col)
    elif st.session_state.page == "inbound":
        inbound_page.render(
            inventory_col=inventory_col, transactions_col=transactions_col
        )
