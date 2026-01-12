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
    
    # Check if user is a customer
    is_customer = (st.session_state.get("user_role") or "").strip().lower() == "customer"
    
    # Location selector for default location (hide for customers)
    if not is_customer:
        cols = get_collections()
        locations_col = cols["locations"]
        
        # Get active locations
        try:
            locs = list(
                locations_col.find({"active": True}, {"_id": 0, "location": 1}).sort(
                    "location", 1
                )
            )
            location_options = [str(d.get("location", "")).strip().upper() for d in locs]
            location_options = [o for o in location_options if o]
            
            # Apply custom sort if available
            try:
                from wms.ui_utils import sort_locations_custom
                location_options = sort_locations_custom(location_options)
            except Exception:
                pass
            
            if location_options:
                st.session_state.default_location = st.sidebar.selectbox(
                    "Default Location",
                    options=[None] + location_options,
                    index=0 if st.session_state.default_location is None else (
                        location_options.index(st.session_state.default_location) + 1
                        if st.session_state.default_location in location_options else 0
                    ),
                    help="Set your working location. This will be the default for Inbound, Outbound, and STO operations.",
                    key="sidebar_default_location"
                )
        except Exception:
            pass
        
        # Audio toggle for SKU scan feedback
        st.session_state.audio_enabled = st.sidebar.toggle(
            "🔊 Audio Feedback",
            value=st.session_state.get("audio_enabled", False),
            help="Enable audio playback of last 4 digits when scanning SKUs",
            key="sidebar_audio_toggle"
        )
    
    st.sidebar.divider()

    if st.sidebar.button("Inventory Dashboard", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        st.session_state.page = "home"
    
    # Hide Master Data, Inbound, Outbound, and STO buttons for customers
    if not is_customer:
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
        st.session_state.default_location = None
        st.session_state.page = "home"
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
        movements_page.render(movement_col=movement_col, mm_col=mm_col)
