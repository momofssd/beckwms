from datetime import datetime

import streamlit as st


def process_scan(*, inventory_col, transactions_col) -> None:
    scan_val = st.session_state.main_scanner
    if not scan_val:
        return

    st.session_state.scan_pair.append(scan_val.strip().upper())
    if len(st.session_state.scan_pair) == 2:
        sku, tracking = st.session_state.scan_pair[0], st.session_state.scan_pair[1]
        loc = st.session_state.current_loc
        ts = datetime.now()

        existing_tx = transactions_col.find_one({"shipment_id": tracking})
        if existing_tx:
            inventory_col.update_one(
                {"sku": existing_tx["sku"], "location": existing_tx["location"]},
                {"$inc": {"quantity": 1}},
            )
            transactions_col.delete_one({"_id": existing_tx["_id"]})
            st.session_state.session_log = [
                l for l in st.session_state.session_log if l["shipment_id"] != tracking
            ]
            st.toast(f"Tracking {tracking} replaced.")

        res = inventory_col.update_one(
            {"sku": sku, "location": loc, "quantity": {"$gt": 0}},
            {"$inc": {"quantity": -1}},
        )
        if res.modified_count > 0:
            inv_doc = inventory_col.find_one(
                {"sku": sku, "location": loc},
                {"_id": 0, "product_name": 1},
            )
            product_name = (
                str((inv_doc or {}).get("product_name", ""))
                .strip()
                .upper()
            )
            entry = {
                "timestamp": ts,
                "sku": sku,
                "product_name": product_name,
                "shipment_id": tracking,
                "location": loc,
                "type": "outbound",
                "outbound_qty": 1,
            }
            transactions_col.insert_one(entry.copy())
            st.session_state.session_log.insert(0, entry)
            st.session_state.last_msg = ("success", f"Processed: {sku}")
        else:
            st.session_state.last_msg = ("error", f"Error: {sku} out of stock at {loc}")
        st.session_state.scan_pair = []

    st.session_state.main_scanner = ""
