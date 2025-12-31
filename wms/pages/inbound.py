from datetime import datetime

import pandas as pd
import streamlit as st


def render(*, inventory_col, transactions_col) -> None:
    st.title("Inbound Entry")


    # --- New inbound flow: scan SKU then manually enter details ---
    st.subheader("Scan SKU Inbound")
    if "inbound_scan_step" not in st.session_state:
        st.session_state.inbound_scan_step = 1
    if "inbound_scanned_sku" not in st.session_state:
        st.session_state.inbound_scanned_sku = ""

    scan_l, scan_r = st.columns([3, 1])
    if st.session_state.inbound_scan_step == 1:
        scan_l.caption("Step 1: Scan SKU label")
        scanned = scan_l.text_input(
            "SCAN_SKU",
            key="inbound_scan_sku_input",
            label_visibility="collapsed",
        )
        if scan_r.button("Next", use_container_width=True):
            cleaned = (scanned or "").strip().upper()
            if not cleaned:
                st.error("Please scan a SKU to continue.")
            else:
                st.session_state.inbound_scanned_sku = cleaned
                st.session_state.inbound_scan_step = 2
                st.rerun()
    else:
        scan_l.caption("Step 2: Enter details and submit")
        scan_l.info(f"Scanned SKU: {st.session_state.inbound_scanned_sku}")
        if scan_r.button("Back", use_container_width=True):
            st.session_state.inbound_scan_step = 1
            st.session_state.inbound_scanned_sku = ""
            st.session_state.inbound_scan_sku_input = ""
            st.rerun()

        with st.form("inbound_scan_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            qty2 = c1.number_input("Quantity", min_value=1, key="inbound_scan_qty")
            name2 = c2.text_input("Product Name", key="inbound_scan_name").upper()
            loc2 = c1.text_input("Location", key="inbound_scan_loc").upper()
            if st.form_submit_button("Submit Scanned Inbound", use_container_width=True):
                sku2 = (st.session_state.inbound_scanned_sku or "").strip().upper()
                if not sku2:
                    st.error("Missing scanned SKU. Click Back and rescan.")
                elif not loc2:
                    st.error("Location is required.")
                else:
                    inventory_col.update_one(
                        {"sku": sku2, "location": loc2},
                        {
                            "$set": {"name": name2},
                            "$inc": {"quantity": int(qty2)},
                        },
                        upsert=True,
                    )
                    transactions_col.insert_one(
                        {
                            "timestamp": datetime.now(),
                            "sku": sku2,
                            "name": name2,
                            "location": loc2,
                            "type": "inbound",
                            "inbound_qty": int(qty2),
                        }
                    )

                    # Reset scan flow back to step 1 for the next item.
                    st.session_state.inbound_scan_step = 1
                    st.session_state.inbound_scanned_sku = ""
                    st.session_state.inbound_scan_sku_input = ""
                    st.success(f"Inbound Successful: {qty2} units of {sku2}")
                    st.rerun()

    st.divider()
    st.subheader("Manual Inbound Entry")
    with st.form("inbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        sku = c1.text_input("SKU").upper()
        name = c2.text_input("Product Name").upper()
        qty = c1.number_input("Quantity", min_value=1)
        loc = c2.text_input("Location").upper()
        if st.form_submit_button("Submit Stock Entry", use_container_width=True):
            inventory_col.update_one(
                {"sku": sku, "location": loc},
                {"$set": {"name": name}, "$inc": {"quantity": int(qty)}},
                upsert=True,
            )
            transactions_col.insert_one(
                {
                    "timestamp": datetime.now(),
                    "sku": sku,
                    "name": name,
                    "location": loc,
                    "type": "inbound",
                    "inbound_qty": int(qty),
                }
            )
            st.success(f"Entry Successful: {qty} units of {sku}")
            st.rerun()

    st.divider()
    st.subheader("Current Inventory Status")
    inventory_data = list(inventory_col.find({}, {"_id": 0}))
    if inventory_data:
        st.dataframe(pd.DataFrame(inventory_data), use_container_width=True)
