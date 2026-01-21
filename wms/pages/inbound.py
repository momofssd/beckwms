from datetime import datetime

import pandas as pd
import streamlit as st

from wms.movement import build_movement_doc, next_inbound_transaction_num
from wms.ui_utils import auto_focus_aria_label_js, sort_locations_custom
from wms.audio_utils import play_last_4_digits


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
        # Fail safe: if Locations collection is missing/misconfigured.
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


def render(*, inventory_col, transactions_col, mm_col, locations_col, movement_col) -> None:
    st.title("Inbound Entry")

    # Initialize active tab in session state
    if "inbound_active_tab" not in st.session_state:
        st.session_state.inbound_active_tab = 0

    tab_inbound, tab_single, tab_manual = st.tabs(["Inbound Multi Entry", "Inbound Single Entry", "Manual Inbound Entry"])

    def _go_to_scan_step_2() -> None:
        """Advance the scan flow to step 2 when the user presses Enter."""
        scanned_local = (st.session_state.get("inbound_scan_sku_input") or "").strip().upper()
        if scanned_local:
            st.session_state.inbound_scanned_sku = scanned_local
            st.session_state.inbound_scan_step = 2
            # Play audio of last 4 digits if enabled
            play_last_4_digits(scanned_local, st.session_state.get("audio_enabled", False))

    location_options = _get_location_options(locations_col)
    sku_options = _get_sku_options(mm_col)
    if not location_options:
        st.warning(
            "No active Locations found. Create locations under Master Data → Locations."
        )
    if not sku_options:
        st.warning("No SKUs found in Material Master. Create materials under Master Data → Materials.")


    with tab_inbound:
        # --- New inbound flow: scan SKU then manually enter details ---
        st.subheader("Scan SKU Inbound")
        if "inbound_scan_step" not in st.session_state:
            st.session_state.inbound_scan_step = 1
        if "inbound_scanned_sku" not in st.session_state:
            st.session_state.inbound_scanned_sku = ""

        scan_l, scan_r = st.columns([3, 1])
        if st.session_state.inbound_scan_step == 1:
            scan_l.caption("Step 1: Scan SKU label")
            # Force the cursor into the scan input (barcode-scanner friendly)
            # by using the shared JS helper.
            auto_focus_aria_label_js("SCAN_SKU")
            # Default focus is on this field; pressing Enter triggers on_change.
            scan_l.text_input(
                "SCAN_SKU",
                key="inbound_scan_sku_input",
                help="Scan a SKU and press Enter",
                label_visibility="collapsed",
                on_change=_go_to_scan_step_2,
            )
            if scan_r.button("Next", use_container_width=True):
                cleaned = (
                    st.session_state.get("inbound_scan_sku_input") or ""
                ).strip().upper()
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
                if location_options:
                    # Use default location if set
                    default_idx = None
                    if st.session_state.get("default_location") and st.session_state.default_location in location_options:
                        default_idx = location_options.index(st.session_state.default_location)
                    
                    loc2 = c1.selectbox(
                        "Location",
                        options=location_options,
                        index=default_idx,
                        key="inbound_scan_loc",
                    )
                else:
                    loc2 = ""
                if st.form_submit_button(
                    "Submit Scanned Inbound", use_container_width=True
                ):
                    sku2 = (st.session_state.inbound_scanned_sku or "").strip().upper()
                    if not sku2:
                        st.error("Missing scanned SKU. Click Back and rescan.")
                        return

                    mm_doc = mm_col.find_one(
                        {"sku": sku2},
                        {"_id": 0, "sku": 1, "product_name": 1, "name": 1, "active": 1},
                    )
                    if not mm_doc:
                        st.error(
                            f"SKU {sku2} is not registered in Material Master (MM). "
                            "Please create it first under Master Data."
                        )
                        return
                    
                    # Check if SKU is active
                    if not mm_doc.get("active", True):
                        st.error(
                            f"SKU {sku2} is deactivated. Please activate it in Master Data before inbound."
                        )
                        return

                    if not loc2:
                        st.error("Location is required.")
                        return

                    name2 = str(
                        mm_doc.get("product_name") or mm_doc.get("name") or ""
                    ).strip().upper()
                    # Movement logging first to get transaction_num
                    try:
                        txn_num = next_inbound_transaction_num(movement_col=movement_col)
                        
                        inventory_col.update_one(
                            {"sku": sku2, "location": loc2},
                            {
                                "$set": {"product_name": name2},
                                "$inc": {"quantity": int(qty2)},
                            },
                            upsert=True,
                        )
                        
                        transactions_col.insert_one(
                            {
                                "timestamp": datetime.now(),
                                "sku": sku2,
                                "product_name": name2,
                                "location": loc2,
                                "type": "inbound",
                                "inbound_qty": int(qty2),
                                "movement_transaction_num": txn_num,
                            }
                        )

                        mv = build_movement_doc(
                            movement_type="inbound",
                            transaction_num=txn_num,
                            qty=int(qty2),
                            location=loc2,
                            details=[
                                {
                                    "timestamp": datetime.now(),
                                    "sku": sku2,
                                    "product_name": name2,
                                    "location": loc2,
                                    "type": "inbound",
                                    "inbound_qty": int(qty2),
                                    "movement_transaction_num": txn_num,
                                }
                            ],
                        )
                        movement_col.insert_one(mv)
                    except Exception as e:
                        st.error(
                            "Inbound failed. Movement logging error: "
                            f"{e}"
                        )
                        return

                    # Reset scan flow back to step 1 for the next item.
                    st.session_state.inbound_scan_step = 1
                    st.session_state.inbound_scanned_sku = ""
                    st.session_state.inbound_scan_sku_input = ""
                    st.success(f"Inbound Successful: {qty2} units of {sku2}")
                    st.rerun()

    with tab_single:
        st.subheader("Inbound Single Entry")
        
        # Initialize session state for single entry
        if "inbound_single_session_log" not in st.session_state:
            st.session_state.inbound_single_session_log = []
        if "inbound_single_session_active" not in st.session_state:
            st.session_state.inbound_single_session_active = False
        if "inbound_single_location" not in st.session_state:
            st.session_state.inbound_single_location = None
        if "inbound_single_last_msg" not in st.session_state:
            st.session_state.inbound_single_last_msg = (None, None)

        def _process_single_scan() -> None:
            """Process a scanned SKU in single entry mode."""
            scanned = (st.session_state.get("inbound_single_scan_input") or "").strip().upper()
            if not scanned:
                return
            
            # Validate SKU exists in master data and is active
            mm_doc = mm_col.find_one(
                {"sku": scanned},
                {"_id": 0, "sku": 1, "product_name": 1, "name": 1, "active": 1},
            )
            if not mm_doc:
                st.session_state.inbound_single_last_msg = (
                    "error",
                    f"SKU {scanned} is not registered in Material Master. Please create it first."
                )
                st.session_state.inbound_single_scan_input = ""
                return
            
            # Check if SKU is active
            if not mm_doc.get("active", True):
                st.session_state.inbound_single_last_msg = (
                    "error",
                    f"SKU {scanned} is deactivated. Please activate it in Master Data before inbound."
                )
                st.session_state.inbound_single_scan_input = ""
                return
            
            # Add to session log
            product_name = str(mm_doc.get("product_name") or mm_doc.get("name") or "").strip().upper()
            st.session_state.inbound_single_session_log.append({
                "timestamp": datetime.now(),
                "sku": scanned,
                "product_name": product_name,
                "qty": 1,
            })
            st.session_state.inbound_single_last_msg = ("success", f"Scanned: {scanned}")
            
            # Store scanned value for audio playback after rerun
            if st.session_state.get("audio_enabled", False):
                st.session_state.inbound_single_audio_pending = scanned
            
            st.session_state.inbound_single_scan_input = ""

        def _confirm_single_session() -> None:
            """Confirm and submit all scanned items in the session."""
            if not st.session_state.inbound_single_session_log:
                st.session_state.inbound_single_last_msg = ("error", "No items to submit.")
                return
            
            location = st.session_state.inbound_single_location
            if not location:
                st.session_state.inbound_single_last_msg = ("error", "Location is required.")
                return
            
            # Aggregate quantities by SKU
            sku_aggregates = {}
            for item in st.session_state.inbound_single_session_log:
                sku = item["sku"]
                if sku not in sku_aggregates:
                    sku_aggregates[sku] = {
                        "product_name": item["product_name"],
                        "qty": 0
                    }
                sku_aggregates[sku]["qty"] += item["qty"]
            
            # Movement logging first to get transaction_num
            try:
                txn_num = next_inbound_transaction_num(movement_col=movement_col)
                
                # Write to database
                details_list = []
                for sku, data in sku_aggregates.items():
                    inventory_col.update_one(
                        {"sku": sku, "location": location},
                        {
                            "$set": {"product_name": data["product_name"]},
                            "$inc": {"quantity": data["qty"]},
                        },
                        upsert=True,
                    )
                    transactions_col.insert_one({
                        "timestamp": datetime.now(),
                        "sku": sku,
                        "product_name": data["product_name"],
                        "location": location,
                        "type": "inbound",
                        "inbound_qty": data["qty"],
                        "movement_transaction_num": txn_num,
                    })
                    details_list.append({
                        "timestamp": datetime.now(),
                        "sku": sku,
                        "product_name": data["product_name"],
                        "location": location,
                        "type": "inbound",
                        "inbound_qty": data["qty"],
                        "movement_transaction_num": txn_num,
                    })
                
                total_qty = sum(d["qty"] for d in sku_aggregates.values())
                mv = build_movement_doc(
                    movement_type="inbound",
                    transaction_num=txn_num,
                    qty=total_qty,
                    location=location,
                    details=details_list,
                )
                movement_col.insert_one(mv)
            except Exception as e:
                st.error(
                    "Inbound failed. Movement logging error: "
                    f"{e}"
                )
                return
            
            st.session_state.inbound_single_last_msg = (
                "success",
                f"Session confirmed! {len(sku_aggregates)} unique SKU(s) submitted."
            )
            # Reset session
            st.session_state.inbound_single_session_log = []
            st.session_state.inbound_single_session_active = False
            st.session_state.inbound_single_location = None

        # Layout: Left column for scanning, Right column for session log
        # On mobile, stack vertically; on desktop, side-by-side
        col_left, col_right = st.columns([1, 1], gap="medium")
        
        with col_left:
            st.subheader("Scan Terminal")
            
            # New Session button
            if st.button("New Session", use_container_width=True, key="inbound_single_new_session"):
                st.session_state.inbound_single_session_log = []
                st.session_state.inbound_single_session_active = True
                st.session_state.inbound_single_location = None
                st.session_state.inbound_single_last_msg = (None, None)
                st.rerun()
            
            # Reset button - only show if session is active
            if st.session_state.inbound_single_session_active:
                if st.button("Reset", use_container_width=True, type="secondary", key="inbound_single_reset"):
                    st.session_state.inbound_single_session_log = []
                    st.session_state.inbound_single_session_active = False
                    st.session_state.inbound_single_location = None
                    st.session_state.inbound_single_last_msg = (None, None)
                    st.rerun()
            
            if not st.session_state.inbound_single_session_active:
                st.info("Click **New Session** to begin scanning.")
            else:
                # Location selection
                if location_options:
                    # Use default location if set
                    default_idx = None
                    if st.session_state.get("default_location") and st.session_state.default_location in location_options:
                        default_idx = location_options.index(st.session_state.default_location)
                    
                    st.session_state.inbound_single_location = st.selectbox(
                        "Select Location",
                        options=location_options,
                        index=default_idx,
                        key="inbound_single_location_select"
                    )
                else:
                    st.warning("No active locations found.")
                
                if st.session_state.inbound_single_location:
                    st.divider()
                    
                    # Display last message
                    msg_data = st.session_state.inbound_single_last_msg
                    if isinstance(msg_data, tuple) and len(msg_data) == 2:
                        msg_t, msg_x = msg_data
                        if msg_t == "success":
                            st.success(msg_x)
                        elif msg_t == "error":
                            st.error(msg_x)
                    
                    # Scan input field with auto-focus
                    st.text_input(
                        "INBOUND_SINGLE_SCAN",
                        key="inbound_single_scan_input",
                        on_change=_process_single_scan,
                        label_visibility="collapsed",
                    )
                    auto_focus_aria_label_js("INBOUND_SINGLE_SCAN")
                    
                    st.info("Scan SKU barcode to add to session...")
                    
                    st.divider()
                    
                    # Confirm button
                    st.button(
                        "Confirm Submit",
                        use_container_width=True,
                        type="primary",
                        disabled=not st.session_state.inbound_single_session_log,
                        on_click=_confirm_single_session,
                        key="inbound_single_confirm"
                    )
        
        # Play audio if there's a pending audio request (after page has rerendered)
        # Place this OUTSIDE the column context to ensure it executes every time
        if st.session_state.get("inbound_single_audio_pending"):
            play_last_4_digits(st.session_state.inbound_single_audio_pending, True)
            # Clear the pending flag
            del st.session_state.inbound_single_audio_pending
        
        with col_right:
            st.subheader("Session Log")
            if st.session_state.inbound_single_session_log:
                # Calculate total quantity
                total_qty = sum(item["qty"] for item in st.session_state.inbound_single_session_log)
                st.caption(f"Items scanned: **{len(st.session_state.inbound_single_session_log)}** | Total Qty: **{total_qty}**")
                
                # Display session log with inline delete functionality
                df_log = pd.DataFrame(st.session_state.inbound_single_session_log)
                df_display = df_log.copy()
                if "timestamp" in df_display.columns:
                    df_display["timestamp"] = pd.to_datetime(
                        df_display["timestamp"], errors="coerce"
                    ).dt.strftime("%Y-%m-%d %H:%M:%S")
                
                # Use data_editor for inline delete functionality
                edited_df = st.data_editor(
                    df_display[["timestamp", "sku", "product_name", "qty"]],
                    use_container_width=True,
                    height=520,
                    hide_index=True,
                    num_rows="dynamic",
                    key="inbound_single_session_log_editor",
                )
                
                # Sync deletions back to session_state
                if len(edited_df) < len(df_display):
                    # User deleted rows - update session_log
                    remaining_indices = edited_df.index.tolist()
                    st.session_state.inbound_single_session_log = [
                        st.session_state.inbound_single_session_log[i] 
                        for i in range(len(st.session_state.inbound_single_session_log))
                        if i in remaining_indices
                    ]
                    st.rerun()
            else:
                st.caption("No scans in this session.")

    with tab_manual:
        st.subheader("Manual Inbound Entry")
        with st.form("inbound_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            if sku_options:
                sku = c1.selectbox("SKU", options=sku_options, index=None)
            else:
                sku = ""
            qty = c1.number_input("Quantity", min_value=1)
            if location_options:
                # Use default location if set
                default_idx = None
                if st.session_state.get("default_location") and st.session_state.default_location in location_options:
                    default_idx = location_options.index(st.session_state.default_location)
                
                loc = c2.selectbox("Location", options=location_options, index=default_idx)
            else:
                loc = ""
            if st.form_submit_button("Submit Stock Entry", use_container_width=True):
                sku_n = (sku or "").strip().upper()
                loc_n = (loc or "").strip().upper()
                if not sku_n:
                    st.error("SKU is required.")
                else:
                    mm_doc = mm_col.find_one(
                        {"sku": sku_n},
                        {"_id": 0, "sku": 1, "product_name": 1, "name": 1},
                    )
                    if not mm_doc:
                        st.error(
                            f"SKU {sku_n} is not registered in Material Master (MM). "
                            "Please create it first under Master Data."
                        )
                    elif not loc_n:
                        st.error("Location is required.")
                    else:
                        name_n = str(
                            mm_doc.get("product_name") or mm_doc.get("name") or ""
                        ).strip().upper()
                        
                        # Movement logging first to get transaction_num
                        try:
                            txn_num = next_inbound_transaction_num(
                                movement_col=movement_col
                            )
                            
                            inventory_col.update_one(
                                {"sku": sku_n, "location": loc_n},
                                {
                                    "$set": {"product_name": name_n},
                                    "$inc": {"quantity": int(qty)},
                                },
                                upsert=True,
                            )
                            transactions_col.insert_one(
                                {
                                    "timestamp": datetime.now(),
                                    "sku": sku_n,
                                    "product_name": name_n,
                                    "location": loc_n,
                                    "type": "inbound",
                                    "inbound_qty": int(qty),
                                    "movement_transaction_num": txn_num,
                                }
                            )

                            mv = build_movement_doc(
                                movement_type="inbound",
                                transaction_num=txn_num,
                                qty=int(qty),
                                location=loc_n,
                                details=[
                                    {
                                        "timestamp": datetime.now(),
                                        "sku": sku_n,
                                        "product_name": name_n,
                                        "location": loc_n,
                                        "type": "inbound",
                                        "inbound_qty": int(qty),
                                        "movement_transaction_num": txn_num,
                                    }
                                ],
                            )
                            movement_col.insert_one(mv)
                            st.success(f"Entry Successful: {qty} units of {sku_n}")
                            st.rerun()
                        except Exception as e:
                            st.error(
                                "Entry failed. Movement logging error: "
                                f"{e}"
                            )

    st.divider()
    st.subheader("Current Inventory Status")
    
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
            st.dataframe(df_inv, use_container_width=True)
        else:
            st.info("No active inventory items with quantity > 0.")
    else:
        st.info("No inventory data available.")
