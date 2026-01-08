from datetime import datetime

import pandas as pd
import streamlit as st

from wms.outbound import confirm_outbound_session, process_scan
from wms.ui_utils import auto_focus_js, to_excel, sort_locations_custom


def _compute_qty(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize transaction quantity into a single signed `qty` column.

    Rules:
    - inbound  -> qty = +inbound_qty
    - outbound -> qty = -outbound_qty

    This keeps exports consistent and avoids separate inbound/outbound columns.
    """
    if df is None or df.empty:
        return df

    df2 = df.copy()
    if "qty" not in df2.columns:
        df2["qty"] = 0

    inbound_mask = df2.get("type").eq("inbound") if "type" in df2.columns else False
    outbound_mask = df2.get("type").eq("outbound") if "type" in df2.columns else False
    void_mask = df2.get("type").eq("void") if "type" in df2.columns else False

    if "inbound_qty" in df2.columns:
        df2.loc[inbound_mask, "qty"] = pd.to_numeric(
            df2.loc[inbound_mask, "inbound_qty"], errors="coerce"
        ).fillna(0)
    if "outbound_qty" in df2.columns:
        df2.loc[outbound_mask, "qty"] = -pd.to_numeric(
            df2.loc[outbound_mask, "outbound_qty"], errors="coerce"
        ).fillna(0)

    # Inventory editor adjustments (reductions/deletions) are logged as type=void.
    # Export these as negative quantities.
    if "void_qty" in df2.columns:
        df2.loc[void_mask, "qty"] = -pd.to_numeric(
            df2.loc[void_mask, "void_qty"], errors="coerce"
        ).fillna(0)

    # Keep qty as an integer when possible for nicer Excel output.
    try:
        df2["qty"] = df2["qty"].astype(int)
    except Exception:
        pass

    return df2


def render(*, inventory_col, transactions_col, movement_col) -> None:
    file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    head_l, head_r = st.columns([3, 1])
    head_l.title("Outbound Terminal")
    if head_r.button("New Session", use_container_width=True):
        st.session_state.session_log, st.session_state.scan_pair = [], []
        st.session_state.outbound_pending = []
        st.session_state.outbound_confirmed = False
        st.session_state.outbound_session_active = True
        st.session_state.last_msg = (None, None)
        st.rerun()

    col_left, col_right = st.columns([1, 1], gap="large")
    with col_left:
        st.subheader("Scan Terminal")
        if not st.session_state.get("outbound_session_active"):
            st.info("Click **New Session** to begin scanning.")
            st.session_state.current_loc = None
            return

        all_locs = inventory_col.distinct("location")
        all_locs_sorted = sort_locations_custom(all_locs)
        st.session_state.current_loc = st.selectbox(
            "Select Station Location", options=all_locs_sorted, index=None
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

            st.divider()
            st.button(
                "Confirm Session Complete",
                use_container_width=True,
                type="primary",
                disabled=(
                    st.session_state.get("outbound_confirmed")
                    or not st.session_state.get("outbound_pending")
                ),
                on_click=lambda: confirm_outbound_session(
                    inventory_col=inventory_col,
                    transactions_col=transactions_col,
                    movement_col=movement_col,
                ),
            )

    with col_right:
        st.subheader("Live Session Log")
        if st.session_state.session_log:
            # Each entry in `session_log` is one scanned/processed item (one row).
            st.caption(f"Items scanned this session: **{len(st.session_state.session_log)}**")
            df_s = pd.DataFrame(st.session_state.session_log)
            # Include optional columns like `product_name` if present (older logs may not have it)
            preferred_cols = [
                "timestamp",
                "sku",
                "product_name",
                "shipment_id",
                "location",
                "type",
                "qty",
            ]
            df_s = _compute_qty(df_s)
            df_s = df_s[[c for c in preferred_cols if c in df_s.columns]]

            # Make timestamps human-readable for the on-screen table while keeping
            # the raw datetime in the export.
            df_display = df_s.copy()
            if "timestamp" in df_display.columns:
                df_display["timestamp"] = pd.to_datetime(
                    df_display["timestamp"], errors="coerce"
                ).dt.strftime("%Y-%m-%d %H:%M:%S")
            st.download_button(
                "Export Session Data",
                data=to_excel(df_s),
                file_name=f"session_{file_ts}.xlsx",
                use_container_width=True,
                disabled=not st.session_state.get("outbound_confirmed"),
            )
            # Keep the on-screen table minimal (but include timestamp)
            base_cols = [
                c
                for c in ["timestamp", "sku", "product_name", "shipment_id"]
                if c in df_display.columns
            ]
            st.dataframe(
                df_display[base_cols].head(15),
                use_container_width=True,
                height=520,
                hide_index=True,
            )
        else:
            st.caption("No scans in this session.")

    st.divider()
    inv_h, btn_tx, btn_stk = st.columns([2, 1, 1])
    inv_h.subheader("Global Inventory Dashboard")

    all_tx_list = list(transactions_col.find({}, {"_id": 0}))
    if all_tx_list:
        df_all_tx = pd.DataFrame(all_tx_list)
        df_all_tx = _compute_qty(df_all_tx)
        cols = [
            "timestamp",
            "sku",
            "product_name",
            "location",
            "type",
            "shipment_id",
            "qty",
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
