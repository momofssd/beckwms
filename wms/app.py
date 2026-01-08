from __future__ import annotations

import streamlit as st

# Local development convenience: load environment variables from `.env`.
# No-op if python-dotenv isn't installed or if `.env` doesn't exist.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from wms.auth import require_auth
from wms.db import get_collections
from wms.session import ensure_session_state_initialized
from wms.ui_utils import disable_scanner_hotkeys
from wms.pages import home as home_page
from wms.pages import inbound as inbound_page
from wms.pages import master_data as master_data_page
from wms.pages import outbound as outbound_page
from wms.pages import sto as sto_page
from wms.pages import transactions as transactions_page
from wms.pages import movements as movements_page


def _reset_inbound_state() -> None:
    """Reset all inbound-related session state."""
    st.session_state.inbound_scan_step = 1
    st.session_state.inbound_scanned_sku = ""
    st.session_state.inbound_scan_sku_input = ""
    st.session_state.inbound_single_session_log = []
    st.session_state.inbound_single_session_active = False
    st.session_state.inbound_single_location = None
    st.session_state.inbound_single_last_msg = (None, None)


def _reset_outbound_state() -> None:
    """Reset all outbound-related session state."""
    st.session_state.session_log = []
    st.session_state.scan_pair = []
    st.session_state.outbound_pending = []
    st.session_state.outbound_confirmed = False
    st.session_state.outbound_session_active = False
    st.session_state.last_msg = (None, None)
    st.session_state.current_loc = None


def render_sidebar() -> None:
    st.sidebar.title(f"Welcome, {st.session_state.username}")
    st.sidebar.caption(
        f"Role: {st.session_state.user_role.upper() if st.session_state.user_role else ''}"
    )
    st.sidebar.divider()

    if st.sidebar.button("Inventory Dashboard", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        st.session_state.page = "home"
    if st.sidebar.button("Master Data", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        st.session_state.page = "master_data"
    if st.sidebar.button("Inbound Entry", use_container_width=True):
        _reset_outbound_state()
        st.session_state.page = "inbound"
    if st.sidebar.button("Outbound Processing", use_container_width=True):
        _reset_inbound_state()
        st.session_state.page = "outbound"
    if st.sidebar.button("STO", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        st.session_state.page = "sto"
    if st.sidebar.button("Transactions", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        st.session_state.page = "transactions"
    if st.sidebar.button("Movements", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        st.session_state.page = "movements"

    st.sidebar.divider()
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()


def run() -> None:
    st.set_page_config(
        page_title="Inv WMS",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    
    # Disable F7 and F12 hotkeys from scanner devices
    disable_scanner_hotkeys()

    cols = get_collections()
    inventory_col = cols["inventory"]
    mm_col = cols["mm"]
    locations_col = cols["locations"]
    transactions_col = cols["transactions"]
    movement_col = cols["movement"]
    users_col = cols["users"]

    ensure_session_state_initialized()
    require_auth(users_col)
    render_sidebar()

    if st.session_state.page == "home":
        home_page.render(
            inventory_col=inventory_col,
            transactions_col=transactions_col,
            movement_col=movement_col,
        )
    elif st.session_state.page == "master_data":
        master_data_page.render(mm_col=mm_col, locations_col=locations_col)
    elif st.session_state.page == "outbound":
        outbound_page.render(
            inventory_col=inventory_col,
            transactions_col=transactions_col,
            movement_col=movement_col,
            mm_col=mm_col,
        )
    elif st.session_state.page == "sto":
        sto_page.render(
            inventory_col=inventory_col,
            transactions_col=transactions_col,
            movement_col=movement_col,
            mm_col=mm_col,
            locations_col=locations_col,
        )
    elif st.session_state.page == "inbound":
        inbound_page.render(
            inventory_col=inventory_col,
            transactions_col=transactions_col,
            mm_col=mm_col,
            locations_col=locations_col,
            movement_col=movement_col,
        )
    elif st.session_state.page == "transactions":
        transactions_page.render(
            inventory_col=inventory_col,
            transactions_col=transactions_col,
            mm_col=mm_col,
            locations_col=locations_col,
        )
    elif st.session_state.page == "movements":
        movements_page.render(movement_col=movement_col)
