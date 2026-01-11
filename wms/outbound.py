from datetime import datetime

import streamlit as st

from wms.movement import build_movement_doc, next_outbound_transaction_num
from wms.audio_utils import play_last_4_digits


def process_scan(*, inventory_col, transactions_col, mm_col) -> None:
    scan_val = st.session_state.main_scanner
    if not scan_val:
        return

    scanned_value = scan_val.strip().upper()
    st.session_state.scan_pair.append(scanned_value)
    
    # Play audio for SKU scan (first scan in the pair)
    if len(st.session_state.scan_pair) == 1:
        play_last_4_digits(scanned_value, st.session_state.get("audio_enabled", False))
    
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

        # NOTE: Duplicated shipment IDs are allowed.
        # Multiple scanned items can share the same shipment_id and should each decrement inventory.

        # Validate SKU is active in Material Master
        mm_doc = mm_col.find_one(
            {"sku": sku},
            {"_id": 0, "active": 1},
        )
        if not mm_doc:
            st.session_state.last_msg = ("error", f"Error: {sku} not found in Material Master")
        elif not mm_doc.get("active", True):
            st.session_state.last_msg = ("error", f"Error: {sku} is deactivated")
        else:
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


def confirm_outbound_session(*, inventory_col, transactions_col, movement_col) -> None:
    """Apply all pending outbound scans to DB and mark session as confirmed."""
    if st.session_state.get("outbound_confirmed"):
        st.session_state.last_msg = ("error", "Session already confirmed.")
        return

    pending = list(st.session_state.get("outbound_pending") or [])
    if not pending:
        st.session_state.last_msg = ("error", "No pending scans to confirm.")
        return

    # Allow duplicated shipment_id:
    # Each pending scan becomes its own transaction document. We do NOT overwrite/delete
    # existing transactions based on shipment_id.

    # Apply updates sequentially (Mongo multi-document transactions may not be enabled).
    # If any item fails (out of stock), we abort before writing transactions.
    for p in pending:
        sku = p.get("sku")
        loc = p.get("location")

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

    # Record movement document (session-level)
    try:
        txn_num = next_outbound_transaction_num(movement_col=movement_col)
        ship_from_loc = str(pending[0].get("location", "")).strip().upper()
        mv = build_movement_doc(
            movement_type="outbound",
            transaction_num=txn_num,
            qty=len(pending),
            location=ship_from_loc,
            details=[p.copy() for p in pending],
        )
        movement_col.insert_one(mv)
    except Exception as e:
        # Movement should not block outbound confirmation.
        st.session_state.last_msg = (
            "error",
            f"Session confirmed, but movement write failed: {e}",
        )
        st.session_state.outbound_confirmed = True
        return

    st.session_state.outbound_confirmed = True
    st.session_state.last_msg = ("success", f"Confirmed session: {len(pending)} item(s) applied.")
