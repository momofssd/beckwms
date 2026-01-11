from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from wms.movement import build_movement_doc, next_sto_transaction_num
from wms.ui_utils import sort_locations_custom


def _get_location_options(locations_col) -> list[str]:
    """Return active locations for dropdown selection with custom sort order."""
    try:
        locs = list(
            locations_col.find({"active": True}, {"_id": 0, "location": 1}).sort(
                "location", 1
            )
        )
        opts = [str(d.get("location", "")).strip().upper() for d in locs]
        opts = [o for o in opts if o]
        # Apply custom sort order
        return sort_locations_custom(opts)
    except Exception:
        return []


def _get_sku_options(mm_col) -> list[str]:
    """Return active SKU options from Material Master (MM)."""
    try:
        # Only return active SKUs
        skus = list(mm_col.find({"active": True}, {"_id": 0, "sku": 1}).sort("sku", 1))
        opts = [str(d.get("sku", "")).strip().upper() for d in skus]
        return [o for o in opts if o]
    except Exception:
        return []


def _available_qty(*, inventory_col, sku: str, location: str) -> int:
    doc = inventory_col.find_one(
        {"sku": str(sku).strip().upper(), "location": str(location).strip().upper()},
        {"_id": 0, "quantity": 1},
    )
    return int((doc or {}).get("quantity", 0) or 0)


def render(*, inventory_col, transactions_col, movement_col, mm_col, locations_col) -> None:
    st.title("STO - Stock Transfer Order")
    st.caption("Transfer stock between locations (creates outbound+inbound style transactions and a STO movement record).")

    location_options = _get_location_options(locations_col)
    sku_options = _get_sku_options(mm_col)
    if not location_options:
        st.warning("No active Locations found. Create locations under Master Data → Locations.")
    if not sku_options:
        st.warning("No SKUs found in Material Master. Create materials under Master Data → Materials.")

    # Keep selections outside the form so we can compute available qty dynamically.
    top_l, top_r = st.columns(2)
    selected_sku = top_l.selectbox("SKU", options=sku_options, index=None)
    if location_options:
        # Use default location if set for "Location From"
        default_from_idx = None
        if st.session_state.get("default_location") and st.session_state.default_location in location_options:
            default_from_idx = location_options.index(st.session_state.default_location)
        
        from_loc = top_r.selectbox("Location From", options=location_options, index=default_from_idx)
        to_options = [l for l in location_options if l != from_loc] if from_loc else location_options
        to_loc = top_r.selectbox("Location To", options=to_options, index=None)
    else:
        from_loc, to_loc = None, None

    avail = 0
    if selected_sku and from_loc:
        avail = _available_qty(inventory_col=inventory_col, sku=selected_sku, location=from_loc)
        st.info(f"Available at {from_loc}: {avail}")

    with st.form("sto_form", clear_on_submit=True):
        qty = st.number_input(
            "Quantity",
            min_value=1,
            max_value=(avail if avail > 0 else 1),
            step=1,
            help="Cannot be more than available qty at Location From.",
        )

        if st.form_submit_button("Submit STO", type="primary", use_container_width=True):
            sku = (selected_sku or "").strip().upper()
            from_loc_n = (from_loc or "").strip().upper()
            to_loc_n = (to_loc or "").strip().upper()

            if not sku:
                st.error("SKU is required (select from dropdown).")
                return
            if not from_loc_n or not to_loc_n:
                st.error("Both From and To locations are required.")
                return
            if from_loc_n == to_loc_n:
                st.error("From and To locations must be different.")
                return

            # Validate SKU exists in MM and is active
            mm_doc = mm_col.find_one(
                {"sku": sku}, {"_id": 0, "sku": 1, "product_name": 1, "name": 1, "active": 1}
            )
            if not mm_doc:
                st.error(f"SKU {sku} is not registered in Material Master. Create it under Master Data.")
                return
            
            # Check if SKU is active
            if not mm_doc.get("active", True):
                st.error(f"SKU {sku} is deactivated. Please activate it in Master Data before STO.")
                return
            
            product_name = str(mm_doc.get("product_name") or mm_doc.get("name") or "").strip().upper()

            # Check sufficient qty at from_loc
            available = _available_qty(inventory_col=inventory_col, sku=sku, location=from_loc_n)
            if available < int(qty):
                st.error(
                    f"Insufficient stock at {from_loc_n}: available={available}, requested={int(qty)}"
                )
                return

            ts = datetime.now()
            shipment_id = ""  # STO can be empty

            outbound_tx = {
                "timestamp": ts,
                "sku": sku,
                "product_name": product_name,
                "shipment_id": shipment_id,
                "location": from_loc_n,
                "type": "outbound",
                "outbound_qty": int(qty),
                "reason": "STO transfer out",
                "sto": True,
                "location_from": from_loc_n,
                "location_to": to_loc_n,
            }
            inbound_tx = {
                "timestamp": ts,
                "sku": sku,
                "product_name": product_name,
                "shipment_id": shipment_id,
                "location": to_loc_n,
                "type": "inbound",
                "inbound_qty": int(qty),
                "reason": "STO transfer in",
                "sto": True,
                "location_from": from_loc_n,
                "location_to": to_loc_n,
            }

            # Apply inventory updates. We do outbound-like decrement first to guarantee stock.
            res = inventory_col.update_one(
                {"sku": sku, "location": from_loc_n, "quantity": {"$gte": int(qty)}},
                {"$inc": {"quantity": -int(qty)}},
            )
            if res.modified_count <= 0:
                st.error("STO failed: could not decrement inventory (stock changed). Please retry.")
                return

            inventory_col.update_one(
                {"sku": sku, "location": to_loc_n},
                {"$set": {"product_name": product_name}, "$inc": {"quantity": int(qty)}},
                upsert=True,
            )

            # Write transactions (outbound+inbound style)
            transactions_col.insert_many([outbound_tx, inbound_tx])

            # Write STO movement document
            try:
                txn_num = next_sto_transaction_num(movement_col=movement_col)
                mv = build_movement_doc(
                    movement_type="sto",
                    transaction_num=txn_num,
                    qty=int(qty),
                    location=from_loc_n,
                    details=[
                        {
                            "timestamp": ts,
                            "sku": sku,
                            "product_name": product_name,
                            "qty": int(qty),
                            "location_from": from_loc_n,
                            "location_to": to_loc_n,
                            "type": "sto",
                            "shipment_id": shipment_id,
                        },
                        {"outbound": outbound_tx},
                        {"inbound": inbound_tx},
                    ],
                )
                mv["delivery_locations"] = {
                    "from": from_loc_n,
                    "to": to_loc_n,
                }
                movement_col.insert_one(mv)
            except Exception as e:
                st.warning(f"STO completed, but movement logging failed: {e}")

            st.success(f"STO completed: {sku} qty {int(qty)} from {from_loc_n} → {to_loc_n}")
            st.rerun()

    st.divider()
    st.subheader("Current Inventory")
    
    # Get all inventory items
    inventory_data = list(inventory_col.find({}, {"_id": 0}))
    
    if inventory_data:
        df_inv = pd.DataFrame(inventory_data)
        
        # Filter: only show items with quantity > 0
        if "quantity" in df_inv.columns:
            df_inv = df_inv[df_inv["quantity"] > 0]
        
        # Filter: only show items whose SKU is active
        if "sku" in df_inv.columns and not df_inv.empty:
            # Get active SKUs from MM collection
            active_skus = set()
            for mm_doc in mm_col.find({}, {"_id": 0, "sku": 1, "active": 1}):
                sku = str(mm_doc.get("sku", "")).strip().upper()
                active = mm_doc.get("active", True)  # Default to True for backward compatibility
                if active and sku:
                    active_skus.add(sku)
            
            # Filter inventory to only include active SKUs
            if active_skus:
                df_inv["sku"] = df_inv["sku"].astype(str).str.strip().str.upper()
                df_inv = df_inv[df_inv["sku"].isin(active_skus)]
        
        if not df_inv.empty:
            st.dataframe(df_inv, use_container_width=True, hide_index=True)
        else:
            st.info("No active inventory items with quantity > 0.")
    else:
        st.caption("No inventory records found.")
