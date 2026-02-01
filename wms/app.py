from __future__ import annotations

import streamlit as st

# Local development convenience: load environment variables from `.env`.
# No-op if python-dotenv isn't installed or if `.env` doesn't exist.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

import os
import pymongo

from wms.auth import require_auth
from wms.db import get_collections
from wms.session import ensure_session_state_initialized
from wms.ui_utils import disable_scanner_hotkeys
from wms.pages import home as home_page
from wms.pages import inbound as inbound_page
from wms.pages import master_data as master_data_page
from wms.pages import outbound as outbound_page
from wms.pages import outbound_load as outbound_load_page
from wms.pages import sto as sto_page
from wms.pages import transactions as transactions_page
from wms.pages import movements as movements_page
from wms.pages import shipment_tracking as shipment_tracking_page


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


def _reset_outbound_load_state() -> None:
    """Reset all outbound load-related session state."""
    st.session_state.outbound_load_session_log = []
    st.session_state.outbound_load_pending = []
    st.session_state.outbound_load_confirmed = False
    st.session_state.outbound_load_session_active = False
    st.session_state.outbound_load_last_msg = (None, None)
    st.session_state.outbound_load_location = None
    st.session_state.outbound_load_sku = None
    st.session_state.outbound_load_extracted_barcodes = []


def _reset_transactions_state() -> None:
    """Reset all transactions-related session state (shipment ID record)."""
    st.session_state.show_shipment_record = False
    st.session_state.shipment_page = 0


def _reset_shipment_tracking_state() -> None:
    """Reset all shipment tracking-related session state."""
    st.session_state.shipment_uploader_key = 0
    st.session_state.label_tracking_page = 0
    st.session_state.label_tracking_numbers = []


def clone_database(source_db_name: str, target_db_name: str) -> tuple[bool, str]:
    """Clone a database from source to target.
    
    Args:
        source_db_name: Name of the source database
        target_db_name: Name of the target database
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            return False, "MONGO_URI not found in environment variables"
        
        client = pymongo.MongoClient(mongo_uri)
        
        source_db = client[source_db_name]
        target_db = client[target_db_name]

        # Get list of all collections in the source database
        collections = source_db.list_collection_names()
        
        if not collections:
            client.close()
            return False, f"No collections found in {source_db_name}"

        # Drop the target database first to avoid duplicate key errors
        client.drop_database(target_db_name)
        
        # Re-reference the target database after dropping
        target_db = client[target_db_name]

        for col_name in collections:
            # Skip system collections
            if col_name.startswith("system."):
                continue
            
            # Fetch all documents from the source collection
            documents = list(source_db[col_name].find())
            
            if documents:
                # Insert documents into the target collection
                target_db[col_name].insert_many(documents)
            else:
                # If collection is empty, just create it
                target_db.create_collection(col_name)

        client.close()
        return True, f"Successfully cloned {source_db_name} to {target_db_name}"

    except Exception as e:
        return False, f"Error cloning database: {str(e)}"


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
        _reset_transactions_state()
        st.session_state.page = "home"
    
    # Hide Master Data, Inbound, Outbound, and STO buttons for customers
    if not is_customer:
        if st.sidebar.button("Master Data", use_container_width=True):
            _reset_inbound_state()
            _reset_outbound_state()
            _reset_transactions_state()
            st.session_state.page = "master_data"
        if st.sidebar.button("Inbound Entry", use_container_width=True):
            _reset_outbound_state()
            _reset_transactions_state()
            st.session_state.page = "inbound"
        if st.sidebar.button("Outbound Processing", use_container_width=True):
            _reset_inbound_state()
            _reset_outbound_load_state()
            _reset_transactions_state()
            st.session_state.page = "outbound"
        if st.sidebar.button("STO", use_container_width=True):
            _reset_inbound_state()
            _reset_outbound_state()
            _reset_transactions_state()
            st.session_state.page = "sto"
    
    if st.sidebar.button("Transactions", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        st.session_state.page = "transactions"
    if st.sidebar.button("Movements", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        _reset_transactions_state()
        st.session_state.page = "movements"
    if st.sidebar.button("Shipment Tracking", use_container_width=True):
        _reset_inbound_state()
        _reset_outbound_state()
        _reset_transactions_state()
        st.session_state.page = "shipment_tracking"

    st.sidebar.divider()
    
    # Clone Database button (only for admin users)
    is_admin = (st.session_state.get("user_role") or "").strip().lower() == "admin"
    if is_admin:
        if st.sidebar.button("🗂️ Clone Database", use_container_width=True):
            with st.spinner("Cloning warehouse_db to warehouse_db_copy..."):
                success, message = clone_database("warehouse_db", "warehouse_db_copy")
                if success:
                    st.sidebar.success(message)
                else:
                    st.sidebar.error(message)
    
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.default_location = None
        st.session_state.page = "home"
        _reset_inbound_state()
        _reset_outbound_state()
        _reset_transactions_state()
        _reset_shipment_tracking_state()
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
            locations_col=locations_col,
        )
    elif st.session_state.page == "outbound_load":
        outbound_load_page.render(
            inventory_col=inventory_col,
            transactions_col=transactions_col,
            movement_col=movement_col,
            mm_col=mm_col,
            locations_col=locations_col,
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
        movements_page.render(
            movement_col=movement_col,
            mm_col=mm_col,
            inventory_col=inventory_col,
            transactions_col=transactions_col,
        )
    elif st.session_state.page == "shipment_tracking":
        shipment_tracking_page.render()
