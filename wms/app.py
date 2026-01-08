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


def render_sidebar() -> None:
    st.sidebar.title(f"Welcome, {st.session_state.username}")
    st.sidebar.caption(
        f"Role: {st.session_state.user_role.upper() if st.session_state.user_role else ''}"
    )
    st.sidebar.divider()

    if st.sidebar.button("Inventory Dashboard", use_container_width=True):
        st.session_state.page = "home"
    if st.sidebar.button("Master Data", use_container_width=True):
        st.session_state.page = "master_data"
    if st.sidebar.button("Inbound Entry", use_container_width=True):
        st.session_state.page = "inbound"
    if st.sidebar.button("Outbound Processing", use_container_width=True):
        st.session_state.page = "outbound"
    if st.sidebar.button("STO", use_container_width=True):
        st.session_state.page = "sto"
    if st.sidebar.button("Transactions", use_container_width=True):
        st.session_state.page = "transactions"
    if st.sidebar.button("Movements", use_container_width=True):
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
    
    # Mobile-optimized CSS
    st.markdown("""
        <style>
        /* Mobile viewport optimization */
        @media (max-width: 768px) {
            /* Reduce padding and margins */
            .block-container {
                padding: 1rem 0.5rem !important;
                max-width: 100% !important;
            }
            
            /* Optimize sidebar for mobile */
            [data-testid="stSidebar"] {
                width: 250px !important;
            }
            
            /* Make buttons more touch-friendly */
            .stButton button {
                min-height: 44px !important;
                font-size: 16px !important;
                padding: 0.5rem 1rem !important;
            }
            
            /* Optimize input fields */
            input, select, textarea {
                font-size: 16px !important;
                min-height: 44px !important;
            }
            
            /* Optimize dataframes */
            [data-testid="stDataFrame"] {
                font-size: 12px !important;
            }
            
            /* Reduce title sizes */
            h1 {
                font-size: 1.5rem !important;
            }
            
            h2 {
                font-size: 1.25rem !important;
            }
            
            h3 {
                font-size: 1.1rem !important;
            }
            
            /* Optimize columns for mobile */
            [data-testid="column"] {
                padding: 0 0.25rem !important;
            }
            
            /* Make tabs more touch-friendly */
            [data-baseweb="tab"] {
                min-height: 44px !important;
                font-size: 14px !important;
            }
            
            /* Optimize number inputs */
            [data-baseweb="input"] {
                font-size: 16px !important;
            }
            
            /* Reduce spacing between elements */
            .element-container {
                margin-bottom: 0.5rem !important;
            }
            
            /* Optimize form spacing */
            [data-testid="stForm"] {
                padding: 0.5rem !important;
            }
            
            /* Make dividers less prominent */
            hr {
                margin: 0.5rem 0 !important;
            }
        }
        
        /* General optimizations for all screen sizes */
        /* Prevent zoom on input focus (iOS) */
        input, select, textarea {
            font-size: 16px !important;
        }
        
        /* Improve touch targets */
        button, a, [role="button"] {
            min-height: 44px !important;
            min-width: 44px !important;
        }
        
        /* Optimize data editor for mobile */
        [data-testid="stDataEditor"] {
            overflow-x: auto !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
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
            inventory_col=inventory_col, transactions_col=transactions_col
        )
    elif st.session_state.page == "movements":
        movements_page.render(movement_col=movement_col)
