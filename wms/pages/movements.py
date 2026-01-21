from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from wms.timezone_utils import utc_to_central
from wms.movement_delete import delete_movement_with_transactions


def render(*, movement_col, mm_col, inventory_col, transactions_col) -> None:
    st.title("Movements")
    st.caption("Session-level movement documents (inbound/outbound/void)")

    mv_list = list(movement_col.find({}).sort("timestamp", -1))
    if not mv_list:
        st.info("No movement records found.")
        return

    # Get list of active SKUs from MM collection
    active_skus = set()
    for mm_doc in mm_col.find({}, {"_id": 0, "sku": 1, "active": 1}):
        sku = str(mm_doc.get("sku", "")).strip().upper()
        active = mm_doc.get("active", True)  # Default to True for backward compatibility
        if active and sku:
            active_skus.add(sku)

    # Filter movements to only include those with active SKUs in their details
    filtered_mv_list = []
    for mv in mv_list:
        details = mv.get("details") or []
        if isinstance(details, list):
            # Check if any detail contains an active SKU
            has_active_sku = False
            for detail in details:
                if isinstance(detail, dict):
                    sku = str(detail.get("sku", "")).strip().upper()
                    if sku in active_skus:
                        has_active_sku = True
                        break
            if has_active_sku:
                filtered_mv_list.append(mv)
        else:
            # If no details, include the movement (e.g., STO movements)
            filtered_mv_list.append(mv)

    if not filtered_mv_list:
        st.info("No movement records found for active SKUs.")
        return

    df = pd.DataFrame(filtered_mv_list)
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])

    # Convert UTC timestamps to US Central Time
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["timestamp"] = df["timestamp"].apply(utc_to_central)

    # --- Filters ---
    with st.container(border=True):
        st.caption("Filters")

        # Date range
        if "timestamp" in df.columns and df["timestamp"].notna().any():
            min_date = df["timestamp"].min().date()
        else:
            min_date = pd.Timestamp.now().date()
        max_date = pd.Timestamp.now().date()

        c1, c2, c3 = st.columns([1, 1, 2])
        start_date = c1.date_input("Start date", value=min_date)
        end_date = c2.date_input("End date", value=max_date)

        # Movement type
        types = (
            sorted(df["movement_type"].dropna().astype(str).str.lower().unique())
            if "movement_type" in df.columns
            else []
        )
        selected_types = c3.multiselect(
            "Movement type",
            options=types,
            default=types,
        )

        # SKU and Location filters - extract unique values from details
        all_skus = set()
        all_loc_from = set()
        all_loc_to = set()

        for mv in filtered_mv_list:
            details = mv.get("details") or []
            if isinstance(details, list):
                for detail in details:
                    if isinstance(detail, dict):
                        # SKU
                        sku = detail.get("sku")
                        if sku:
                            sku_upper = str(sku).strip().upper()
                            # Only include active SKUs in the filter options
                            if sku_upper in active_skus:
                                all_skus.add(sku_upper)
                        
                        # Location From
                        lf = detail.get("location_from")
                        if lf:
                            all_loc_from.add(str(lf).strip().upper())
                        
                        # Location To
                        lt = detail.get("location_to")
                        if lt:
                            all_loc_to.add(str(lt).strip().upper())
        
        sku_options = sorted(list(all_skus))
        selected_skus = st.multiselect(
            "SKU Filter",
            options=sku_options,
            default=[],
            help="Filter movements by SKU (searches within details)"
        )

        c_loc1, c_loc2 = st.columns(2)
        selected_loc_from = c_loc1.multiselect(
            "Location From",
            options=sorted(list(all_loc_from)),
            default=[],
        )
        selected_loc_to = c_loc2.multiselect(
            "Location To",
            options=sorted(list(all_loc_to)),
            default=[],
        )

    df_filtered = df.copy()
    if "timestamp" in df_filtered.columns:
        ts = pd.to_datetime(df_filtered["timestamp"], errors="coerce")
        df_filtered = df_filtered[ts.dt.date.between(start_date, end_date)]
    if selected_types and "movement_type" in df_filtered.columns:
        df_filtered = df_filtered[
            df_filtered["movement_type"].astype(str).str.lower().isin(selected_types)
        ]
    
    # Apply SKU filter - filter movements that contain ALL of the selected SKUs in their details (AND condition)
    if selected_skus:
        filtered_txn_nums = set()
        for mv in filtered_mv_list:
            details = mv.get("details") or []
            if isinstance(details, list):
                # Collect all SKUs in this movement's details
                movement_skus = set()
                for detail in details:
                    if isinstance(detail, dict):
                        sku = str(detail.get("sku", "")).strip().upper()
                        if sku:
                            movement_skus.add(sku)
                
                # Check if ALL selected SKUs are present in this movement (AND condition)
                if all(selected_sku in movement_skus for selected_sku in selected_skus):
                    txn_num = mv.get("transaction_num")
                    if txn_num is not None:
                        filtered_txn_nums.add(str(txn_num))
        
        if "transaction_num" in df_filtered.columns:
            df_filtered = df_filtered[
                df_filtered["transaction_num"].astype(str).isin(filtered_txn_nums)
            ]
        else:
            # If no transaction_num column, show no results
            df_filtered = df_filtered.iloc[0:0]

    # Apply Location From filter (OR condition: match if any detail has one of the selected locations)
    if selected_loc_from:
        matching_txns = set()
        for mv in filtered_mv_list:
            details = mv.get("details")
            if isinstance(details, list):
                for d in details:
                    if isinstance(d, dict) and str(d.get("location_from", "")).strip().upper() in selected_loc_from:
                        matching_txns.add(str(mv.get("transaction_num")))
                        break
        
        if "transaction_num" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["transaction_num"].astype(str).isin(matching_txns)]
        else:
             df_filtered = df_filtered.iloc[0:0]

    # Apply Location To filter (OR condition)
    if selected_loc_to:
        matching_txns = set()
        for mv in filtered_mv_list:
            details = mv.get("details")
            if isinstance(details, list):
                for d in details:
                    if isinstance(d, dict) and str(d.get("location_to", "")).strip().upper() in selected_loc_to:
                        matching_txns.add(str(mv.get("transaction_num")))
                        break
        
        if "transaction_num" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["transaction_num"].astype(str).isin(matching_txns)]
        else:
             df_filtered = df_filtered.iloc[0:0]

    # Add a compact preview column for details; the full details are shown below.
    def _details_preview(x) -> str:
        try:
            n = len(x) if isinstance(x, list) else 0
        except Exception:
            n = 0
        return f"{n} row(s)" if n else ""

    if "details" in df_filtered.columns:
        df_filtered["details"] = df_filtered["details"].apply(_details_preview)
    else:
        df_filtered["details"] = ""

    # Delivery Locations for STO (keep as a simple column; do NOT expand details).
    def _dl_to(x) -> str:
        """Coerce delivery_locations to a display string.

        Streamlit Cloud can sometimes infer object columns and render dicts as JSON.
        This forces a plain string for consistent rendering.
        """

        try:
            # Treat pandas NaN as empty
            try:
                if pd.isna(x):
                    return ""
            except Exception:
                pass

            if isinstance(x, dict):
                return str(x.get("to", "")).strip().upper()
            # If it arrives as a stringified dict, try a light parse.
            if isinstance(x, str) and x.strip().startswith("{") and "\"to\"" in x:
                try:
                    j = json.loads(x)
                    if isinstance(j, dict):
                        return str(j.get("to", "")).strip().upper()
                except Exception:
                    pass
            if x is None:
                return ""
            s = str(x).strip()
            if s.lower() in {"nan", "none"}:
                return ""
            return s.upper()
        except Exception:
            return ""

    if "delivery_locations" in df_filtered.columns:
        df_filtered["delivery_locations"] = df_filtered["delivery_locations"].apply(_dl_to)
    else:
        df_filtered["delivery_locations"] = ""

    # Force dtype to string to avoid Streamlit rendering it as JSON/object.
    try:
        df_filtered["delivery_locations"] = df_filtered["delivery_locations"].astype(str)
    except Exception:
        pass

    cols = [
        c
        for c in [
            "timestamp",
            "movement_type",
            "transaction_num",
            "qty",
            "location",
            "delivery_locations",
            "details",
        ]
        if c in df_filtered.columns
    ]
    extra_cols = [c for c in df_filtered.columns if c not in cols]

    # Search input (no dropdown): user types a movement transaction number.
    # Default is empty.
    selected_txn = st.text_input(
        "transaction_num (type to view details)",
        value="",
        placeholder="e.g. 100001 or 20000001 or 3001",
    ).strip()

    # Filter the dataframe to show only the selected transaction_num if provided
    df_display = df_filtered.copy()
    if selected_txn:
        if "transaction_num" in df_display.columns:
            df_display = df_display[df_display["transaction_num"].astype(str) == selected_txn]
    
    st.dataframe(
        df_display[cols + extra_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            # Keep a consistent header name
            "details": st.column_config.TextColumn(
                "details", help="Select a transaction_num above to view full details"
            ),
            "transaction_num": st.column_config.TextColumn(
                "transaction_num", help="Select this transaction_num above to view details"
            ),
        },
    )

    st.divider()
    st.subheader("Details")
    if not selected_txn:
        st.caption("Type a transaction_num above to view its details.")
        return

    # Look up the selected movement from the filtered list (only active SKUs)
    selected_mv = next(
        (mv for mv in filtered_mv_list if str(mv.get("transaction_num", "")) == selected_txn),
        None,
    )
    if not selected_mv:
        st.warning(f"No movement found for transaction_num={selected_txn}")
        return
    
    # Add delete button for admin users
    user_role = (st.session_state.get("user_role") or "").strip().lower()
    if user_role == "admin":
        st.warning("⚠️ **Admin Action**: Delete this movement will reverse all inventory changes and remove related transactions.")
        
        col_delete_1, col_delete_2, col_delete_3 = st.columns([1, 1, 2])
        if col_delete_1.button("🗑️ Delete Movement", type="secondary", use_container_width=True):
            st.session_state.confirm_delete_movement = selected_txn
            st.rerun()
        
        # Confirmation dialog
        if st.session_state.get("confirm_delete_movement") == selected_txn:
            col_delete_2.markdown("**Confirm deletion?**")
            col_confirm_1, col_confirm_2 = col_delete_2.columns(2)
            
            if col_confirm_1.button("✅ Yes", type="primary", key="confirm_yes"):
                success, message = delete_movement_with_transactions(
                    movement_col=movement_col,
                    transactions_col=transactions_col,
                    inventory_col=inventory_col,
                    transaction_num=selected_txn,
                )
                if success:
                    st.success(message)
                    del st.session_state.confirm_delete_movement
                    st.rerun()
                else:
                    st.error(message)
                    del st.session_state.confirm_delete_movement
            
            if col_confirm_2.button("❌ No", key="confirm_no"):
                del st.session_state.confirm_delete_movement
                st.rerun()
        
        st.divider()

    details = (selected_mv or {}).get("details") or []
    if not isinstance(details, list) or len(details) == 0:
        st.caption("No details")
        return

    # For STO: Show details with SKU and product_name from the details array
    if str((selected_mv or {}).get("movement_type", "")).strip().lower() == "sto":
        # Extract SKU and product_name from details, filtering out empty objects
        sto_details = []
        for detail in details:
            if isinstance(detail, dict):
                # Only include details that have SKU (filter out empty wrapper objects)
                sku = str(detail.get("sku", "")).strip().upper()
                if sku:  # Only add if SKU exists
                    sto_details.append({
                        "sku": sku,
                        "product_name": str(detail.get("product_name", "")).strip().upper(),
                        "qty": detail.get("qty", 0),
                        "location_from": str(detail.get("location_from", "")).strip().upper(),
                        "location_to": str(detail.get("location_to", "")).strip().upper(),
                    })
        
        if sto_details:
            df_sto = pd.DataFrame(sto_details)
            st.dataframe(df_sto, use_container_width=True, hide_index=True)
        else:
            st.caption("No STO details available")
        return

    # Otherwise: deconstruct (normalize) the embedded details objects into a table.
    try:
        df_details = pd.json_normalize(details)
        # Convert timestamps to US Central Time
        if "timestamp" in df_details.columns:
            df_details["timestamp"] = pd.to_datetime(
                df_details["timestamp"], errors="coerce"
            )
            df_details["timestamp"] = df_details["timestamp"].apply(utc_to_central)
            df_details["timestamp"] = df_details["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_details, use_container_width=True, hide_index=True)
    except Exception:
        st.code(json.dumps(details, default=str, indent=2), language="json")
