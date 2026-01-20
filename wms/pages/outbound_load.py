from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from wms.movement import build_movement_doc, next_outbound_transaction_num
from wms.ui_utils import auto_focus_js, to_excel, sort_locations_custom
from wms.ups_tracking_pattern import _extract_tracking_numbers_from_text

# Barcode scanning imports
try:
    from pdf2image import convert_from_bytes
    from pyzbar import pyzbar
    import pdfplumber
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False


def _extract_barcodes_from_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Extract 1D barcodes from each page of a PDF.
    Returns a list of dicts with page number and unique barcodes found on that page.
    """
    if not BARCODE_AVAILABLE:
        return []
    
    results = []
    try:
        images = convert_from_bytes(pdf_bytes, dpi=200)
        for page_num, img in enumerate(images, start=1):
            barcodes = pyzbar.decode(img)
            page_barcodes = set()  # Use set to remove duplicates within the same page
            
            for barcode in barcodes:
                try:
                    # Only process 1D barcodes
                    if barcode.type in ['CODE128', 'CODE39', 'EAN13', 'EAN8', 'UPCA', 'UPCE', 'I25', 'CODE93']:
                        data = barcode.data.decode('utf-8').strip()
                        if data:
                            # Extract tracking numbers using the pattern from ups_tracking_pattern
                            extracted_tracking = _extract_tracking_numbers_from_text(data)
                            if extracted_tracking:
                                # Use the extracted tracking number (should be 22 digits)
                                for tracking in extracted_tracking:
                                    page_barcodes.add(tracking)
                            else:
                                # If no pattern match, use the raw barcode data
                                page_barcodes.add(data)
                except Exception:
                    continue
            
            # Add each unique barcode from this page
            for barcode_data in page_barcodes:
                results.append({
                    'page': page_num,
                    'barcode': barcode_data
                })
    except Exception as e:
        st.error(f"Error extracting barcodes: {e}")
        return []
    
    return results


def _compute_qty(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize transaction quantity into a single signed `qty` column."""
    if df is None or df.empty:
        return df

    df2 = df.copy()
    if "qty" not in df2.columns:
        df2["qty"] = 0

    outbound_mask = df2.get("type").eq("outbound") if "type" in df2.columns else False

    if "outbound_qty" in df2.columns:
        df2.loc[outbound_mask, "qty"] = -pd.to_numeric(
            df2.loc[outbound_mask, "outbound_qty"], errors="coerce"
        ).fillna(0)

    try:
        df2["qty"] = df2["qty"].astype(int)
    except Exception:
        pass

    return df2


def confirm_outbound_load_session(*, inventory_col, transactions_col, movement_col) -> None:
    """Apply all pending outbound load scans to DB and mark session as confirmed."""
    if st.session_state.get("outbound_load_confirmed"):
        st.session_state.outbound_load_last_msg = ("error", "Session already confirmed.")
        return

    pending = list(st.session_state.get("outbound_load_pending") or [])
    if not pending:
        st.session_state.outbound_load_last_msg = ("error", "No pending items to confirm.")
        return

    # Apply updates sequentially
    for p in pending:
        sku = p.get("sku")
        loc = p.get("location")

        res = inventory_col.update_one(
            {"sku": sku, "location": loc, "quantity": {"$gt": 0}},
            {"$inc": {"quantity": -1}},
        )
        if res.modified_count <= 0:
            st.session_state.outbound_load_last_msg = (
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
        st.session_state.outbound_load_last_msg = (
            "error",
            f"Session confirmed, but movement write failed: {e}",
        )
        st.session_state.outbound_load_confirmed = True
        return

    st.session_state.outbound_load_confirmed = True
    st.session_state.outbound_load_last_msg = ("success", f"Confirmed session: {len(pending)} item(s) applied.")


def render(*, inventory_col, transactions_col, movement_col, mm_col, locations_col) -> None:
    file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    head_l, head_r = st.columns([3, 1])
    head_l.title("Outbound Load Terminal")
    
    # New Session button
    if head_r.button("New Session", use_container_width=True, key="outbound_load_new_session"):
        st.session_state.outbound_load_session_log = []
        st.session_state.outbound_load_pending = []
        st.session_state.outbound_load_confirmed = False
        st.session_state.outbound_load_session_active = True
        st.session_state.outbound_load_last_msg = (None, None)
        st.session_state.outbound_load_location = None
        st.session_state.outbound_load_sku = None
        st.session_state.outbound_load_extracted_barcodes = []
        st.rerun()
    
    # Reset button - only show if session is active
    if st.session_state.get("outbound_load_session_active"):
        if head_r.button("Reset", use_container_width=True, type="secondary", key="outbound_load_reset"):
            st.session_state.outbound_load_session_log = []
            st.session_state.outbound_load_pending = []
            st.session_state.outbound_load_confirmed = False
            st.session_state.outbound_load_session_active = False
            st.session_state.outbound_load_last_msg = (None, None)
            st.session_state.outbound_load_location = None
            st.session_state.outbound_load_sku = None
            st.session_state.outbound_load_extracted_barcodes = []
            st.rerun()

    col_left, col_right = st.columns([1, 1], gap="large")
    
    with col_left:
        st.subheader("Batch Upload Terminal")
        
        if not st.session_state.get("outbound_load_session_active"):
            st.info("Click **New Session** to begin batch upload.")
            return

        if not BARCODE_AVAILABLE:
            st.error("Barcode scanning unavailable. Install: pip install pyzbar pdf2image pillow pdfplumber")
            return

        # Step 1: Location Selection
        st.markdown("**Step 1: Select Location**")
        all_locs = list(locations_col.find({"active": True}, {"_id": 0, "location": 1}).sort("location", 1))
        location_options = [str(d.get("location", "")).strip().upper() for d in all_locs]
        location_options = [o for o in location_options if o]
        location_options = sort_locations_custom(location_options)
        
        # Use default location if set
        default_idx = None
        if st.session_state.get("default_location") and st.session_state.default_location in location_options:
            default_idx = location_options.index(st.session_state.default_location)
        
        st.session_state.outbound_load_location = st.selectbox(
            "Select Station Location",
            options=location_options,
            index=default_idx,
            key="outbound_load_location_select"
        )
        
        st.divider()
        
        # Step 2: SKU Selection
        st.markdown("**Step 2: Select SKU**")
        
        # Get active SKUs from material master
        active_skus = []
        for mm_doc in mm_col.find({"active": True}, {"_id": 0, "sku": 1, "product_name": 1}).sort("sku", 1):
            sku = str(mm_doc.get("sku", "")).strip().upper()
            product_name = str(mm_doc.get("product_name", "")).strip().upper()
            if sku:
                display_text = f"{sku} - {product_name}" if product_name else sku
                active_skus.append((sku, display_text))
        
        if not active_skus:
            st.warning("No active SKUs found in Material Master.")
            return
        
        sku_display_options = [display for _, display in active_skus]
        sku_values = [sku for sku, _ in active_skus]
        
        selected_sku_idx = st.selectbox(
            "Select SKU (Active Only)",
            options=range(len(sku_display_options)),
            format_func=lambda i: sku_display_options[i],
            key="outbound_load_sku_select"
        )
        
        st.session_state.outbound_load_sku = sku_values[selected_sku_idx]
        
        st.divider()
        
        # Step 3: PDF Upload
        st.markdown("**Step 3: Upload Shipment Labels (PDF)**")
        st.caption("Each page should contain one shipment label with a barcode.")
        
        uploaded_file = st.file_uploader(
            "Drag or upload PDF file",
            type=["pdf"],
            key="outbound_load_pdf_uploader"
        )
        
        if uploaded_file:
            if st.button("Process PDF", use_container_width=True, type="primary", key="outbound_load_process_pdf"):
                with st.spinner("Extracting barcodes from PDF..."):
                    pdf_bytes = uploaded_file.getvalue()
                    extracted = _extract_barcodes_from_pdf(pdf_bytes)
                    
                    if not extracted:
                        st.session_state.outbound_load_last_msg = ("error", "No barcodes found in PDF.")
                    else:
                        st.session_state.outbound_load_extracted_barcodes = extracted
                        
                        # Create session log entries
                        sku = st.session_state.outbound_load_sku
                        loc = st.session_state.outbound_load_location
                        
                        # Get product name from material master
                        mm_doc = mm_col.find_one({"sku": sku}, {"_id": 0, "product_name": 1})
                        product_name = str((mm_doc or {}).get("product_name", "")).strip().upper()
                        
                        # Check inventory availability
                        inv_doc = inventory_col.find_one(
                            {"sku": sku, "location": loc},
                            {"_id": 0, "quantity": 1}
                        )
                        available_qty = int((inv_doc or {}).get("quantity", 0) or 0)
                        
                        if available_qty < len(extracted):
                            st.session_state.outbound_load_last_msg = (
                                "error",
                                f"Insufficient inventory: {available_qty} available, {len(extracted)} required."
                            )
                        else:
                            # Create entries for each barcode (in order from first page to last)
                            for item in extracted:
                                ts = datetime.now()
                                entry = {
                                    "timestamp": ts,
                                    "sku": sku,
                                    "product_name": product_name,
                                    "shipment_id": item['barcode'],
                                    "location": loc,
                                    "type": "outbound",
                                    "outbound_qty": 1,
                                }
                                st.session_state.outbound_load_pending.append(entry)
                                st.session_state.outbound_load_session_log.append(entry)
                            
                            st.session_state.outbound_load_last_msg = (
                                "success",
                                f"Processed {len(extracted)} shipment label(s)."
                            )
                st.rerun()
        
        st.divider()
        
        # Display messages
        msg_data = st.session_state.get("outbound_load_last_msg", (None, None))
        if isinstance(msg_data, tuple) and len(msg_data) == 2:
            msg_t, msg_x = msg_data
            if msg_t == "success":
                st.success(msg_x)
            if msg_t == "error":
                st.error(msg_x)
        
        # Confirm button
        st.button(
            "Confirm Session Complete",
            use_container_width=True,
            type="primary",
            disabled=(
                st.session_state.get("outbound_load_confirmed")
                or not st.session_state.get("outbound_load_pending")
            ),
            on_click=lambda: confirm_outbound_load_session(
                inventory_col=inventory_col,
                transactions_col=transactions_col,
                movement_col=movement_col,
            ),
            key="outbound_load_confirm_btn"
        )

    with col_right:
        st.subheader("Live Session Log")
        
        if st.session_state.get("outbound_load_session_log"):
            session_log = st.session_state.outbound_load_session_log
            st.caption(f"Items ready to outbound: **{len(session_log)}**")
            
            df_s = pd.DataFrame(session_log)
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

            # Make timestamps human-readable
            df_display = df_s.copy()
            if "timestamp" in df_display.columns:
                df_display["timestamp"] = pd.to_datetime(
                    df_display["timestamp"], errors="coerce"
                ).dt.strftime("%Y-%m-%d %H:%M:%S")
            
            st.download_button(
                "Export Session Data",
                data=to_excel(df_s),
                file_name=f"outbound_load_session_{file_ts}.xlsx",
                use_container_width=True,
                disabled=not st.session_state.get("outbound_load_confirmed"),
                key="outbound_load_export_btn"
            )
            
            # Display session log
            if not st.session_state.get("outbound_load_confirmed"):
                base_cols = [
                    c
                    for c in ["timestamp", "sku", "product_name", "shipment_id"]
                    if c in df_display.columns
                ]
                edited_df = st.data_editor(
                    df_display[base_cols].head(15),
                    use_container_width=True,
                    height=520,
                    hide_index=True,
                    num_rows="dynamic",
                    key="outbound_load_session_log_editor",
                )
                
                # Sync deletions back to session_state
                if len(edited_df) < len(df_display[base_cols].head(15)):
                    remaining_indices = edited_df.index.tolist()
                    st.session_state.outbound_load_session_log = [
                        st.session_state.outbound_load_session_log[i] 
                        for i in range(min(15, len(st.session_state.outbound_load_session_log)))
                        if i in remaining_indices
                    ] + st.session_state.outbound_load_session_log[15:]
                    
                    st.session_state.outbound_load_pending = [
                        st.session_state.outbound_load_pending[i] 
                        for i in range(min(15, len(st.session_state.outbound_load_pending)))
                        if i in remaining_indices
                    ] + st.session_state.outbound_load_pending[15:]
                    st.rerun()
            else:
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
            st.caption("No items in this session.")
        
        # Display extracted barcodes details
        if st.session_state.get("outbound_load_extracted_barcodes"):
            st.divider()
            st.markdown("**Extracted Barcodes**")
            extracted = st.session_state.outbound_load_extracted_barcodes
            
            df_barcodes = pd.DataFrame(extracted)
            st.dataframe(
                df_barcodes,
                use_container_width=True,
                hide_index=True,
            )
