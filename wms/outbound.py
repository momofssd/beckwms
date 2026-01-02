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

        # Session-based behavior:
        # - Each scan pair adds a pending transaction and logs it.
        # - No DB changes happen here; DB is only updated on "Confirm Session Complete".
        # - We still validate against current inventory to prevent obvious out-of-stock scans.
        if st.session_state.get("outbound_confirmed"):
            st.session_state.last_msg = (
                "error",
                "Session already confirmed. Click New Session to start another.",
            )
            st.session_state.scan_pair = []
            st.session_state.main_scanner = ""
            return

        if tracking in {x.get("shipment_id") for x in st.session_state.get("outbound_pending", [])}:
            st.session_state.last_msg = (
                "error",
                f"Duplicate Shipment ID in this session: {tracking}",
            )
            st.session_state.scan_pair = []
            st.session_state.main_scanner = ""
            return

        inv_doc = inventory_col.find_one(
            {"sku": sku, "location": loc},
            {"_id": 0, "product_name": 1, "quantity": 1},
        )
        qty = int((inv_doc or {}).get("quantity", 0) or 0)
        if qty <= 0:
            st.session_state.last_msg = ("error", f"Error: {sku} out of stock at {loc}")
        else:
            product_name = str((inv_doc or {}).get("product_name", "")).strip().upper()
            entry = {
                "timestamp": ts,
                "sku": sku,
                "product_name": product_name,
                "shipment_id": tracking,
                "location": loc,
                "type": "outbound",
                "outbound_qty": 1,
            }
            st.session_state.outbound_pending.insert(0, entry)
            st.session_state.session_log.insert(0, entry)
            st.session_state.last_msg = ("success", f"Queued: {sku}")
        st.session_state.scan_pair = []

    st.session_state.main_scanner = ""


def confirm_outbound_session(*, inventory_col, transactions_col) -> None:
    """Apply all pending outbound scans to DB and mark session as confirmed."""
    if st.session_state.get("outbound_confirmed"):
        st.session_state.last_msg = ("error", "Session already confirmed.")
        return

    pending = list(st.session_state.get("outbound_pending") or [])
    if not pending:
        st.session_state.last_msg = ("error", "No pending scans to confirm.")
        return

    # Overwrite behavior:
    # If a shipment_id already exists in DB, we delete/replace it and keep the latest timestamp.
    # To keep inventory correct, we reverse the old transaction's inventory impact before
    # applying the new outbound decrement.

    # Apply updates sequentially (Mongo multi-document transactions may not be enabled).
    # If any item fails (out of stock), we abort before writing transactions.
    for p in pending:
        sku = p.get("sku")
        loc = p.get("location")
        shipment_id = p.get("shipment_id")

        existing_tx = transactions_col.find_one({"shipment_id": shipment_id})
        if existing_tx:
            # Reverse inventory based on the existing transaction type.
            # outbound -> add back 1, inbound -> subtract 1, void -> treat as subtract (safe default)
            if existing_tx.get("type") == "outbound":
                inventory_col.update_one(
                    {"sku": existing_tx.get("sku"), "location": existing_tx.get("location")},
                    {"$inc": {"quantity": 1}},
                )
            elif existing_tx.get("type") == "inbound":
                inventory_col.update_one(
                    {"sku": existing_tx.get("sku"), "location": existing_tx.get("location")},
                    {"$inc": {"quantity": -1}},
                )
            elif existing_tx.get("type") == "void":
                # Existing code treats void as negative qty on export; safest reversal here is -1.
                inventory_col.update_one(
                    {"sku": existing_tx.get("sku"), "location": existing_tx.get("location")},
                    {"$inc": {"quantity": -1}},
                )

            transactions_col.delete_one({"_id": existing_tx.get("_id")})

        res = inventory_col.update_one(
            {"sku": sku, "location": loc, "quantity": {"$gt": 0}},
            {"$inc": {"quantity": -1}},
        )
        if res.modified_count <= 0:
            st.session_state.last_msg = (
                "error",
                f"Confirm failed: {sku} out of stock at {loc}. (Session not confirmed.)",
            )
            return

    # Record transactions after inventory succeeded
    transactions_col.insert_many([p.copy() for p in pending])
    st.session_state.outbound_confirmed = True
    st.session_state.last_msg = ("success", f"Confirmed session: {len(pending)} item(s) applied.")
