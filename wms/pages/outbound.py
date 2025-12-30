from datetime import datetime

import pandas as pd
import streamlit as st

from wms.outbound import process_scan
from wms.ui_utils import auto_focus_js, to_excel


def render(*, inventory_col, transactions_col) -> None:
    file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    head_l, head_r = st.columns([3, 1])
    head_l.title("Outbound Terminal")
    if head_r.button("New Session", use_container_width=True):
        st.session_state.session_log, st.session_state.scan_pair = [], []
        st.session_state.last_msg = (None, None)
        st.rerun()

    col_left, col_right = st.columns([1, 1], gap="large")
    with col_left:
        st.subheader("Scan Terminal")
        all_locs = sorted(inventory_col.distinct("location"))
        st.session_state.current_loc = st.selectbox(
            "Select Station Location", options=all_locs, index=None
        )
        if st.session_state.current_loc:
            st.divider()
            msg_data = st.session_state.get("last_msg", (None, None))
            if isinstance(msg_data, tuple) and len(msg_data) == 2:
                msg_t, msg_x = msg_data
                if msg_t == "success":
                    st.success(msg_x)
                if msg_t == "error":
                    st.error(msg_x)

            st.text_input(
                "SCAN_ZONE",
                key="main_scanner",
                on_change=lambda: process_scan(
                    inventory_col=inventory_col, transactions_col=transactions_col
                ),
                label_visibility="collapsed",
            )
            auto_focus_js()
            if len(st.session_state.scan_pair) == 0:
                st.info("Awaiting SKU scan...")
            else:
                st.warning(
                    f"SKU {st.session_state.scan_pair[0]} captured. Scan Shipment ID now."
                )

    with col_right:
        st.subheader("Live Session Log")
        if st.session_state.session_log:
            df_s = pd.DataFrame(st.session_state.session_log)
            # Include optional columns like `name` if present (older logs may not have it)
            preferred_cols = [
                "timestamp",
                "sku",
                "shipment_id",
                "location",
                "type",
                "outbound_qty",
            ]
            df_s = df_s[[c for c in preferred_cols if c in df_s.columns]]
            st.download_button(
                "Export Session Data",
                data=to_excel(df_s),
                file_name=f"session_{file_ts}.xlsx",
                use_container_width=True,
            )
            # Keep the on-screen table minimal
            base_cols = [c for c in ["sku", "name", "shipment_id"] if c in df_s.columns]
            st.table(df_s[base_cols])
        else:
            st.caption("No scans in this session.")

    st.divider()
    inv_h, btn_tx, btn_stk = st.columns([2, 1, 1])
    inv_h.subheader("Global Inventory Dashboard")

    all_tx_list = list(transactions_col.find({}, {"_id": 0}))
    if all_tx_list:
        df_all_tx = pd.DataFrame(all_tx_list)
        cols = [
            "timestamp",
            "sku",
            "location",
            "type",
            "shipment_id",
            "outbound_qty",
            "inbound_qty",
        ]
        existing_cols = [c for c in cols if c in df_all_tx.columns]
        df_all_tx = df_all_tx[existing_cols]
        btn_tx.download_button(
            "Export Transactions",
            data=to_excel(df_all_tx),
            file_name=f"all_transactions_{file_ts}.xlsx",
            use_container_width=True,
        )

    inventory_data = list(inventory_col.find({}, {"_id": 0}))
    if inventory_data:
        df_inv = pd.DataFrame(inventory_data)
        btn_stk.download_button(
            "Export Current Stock",
            data=to_excel(df_inv),
            file_name=f"inventory_{file_ts}.xlsx",
            use_container_width=True,
        )
        st.dataframe(df_inv, use_container_width=True)
