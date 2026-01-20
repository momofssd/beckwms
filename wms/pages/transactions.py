from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from wms.timezone_utils import utc_to_central
from wms.ups_tracking_pattern import _is_valid_usps_tracking, _extract_tracking_numbers_from_text


def _compute_qty(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize transaction quantity into a single signed `qty` column.

    Rules:
    - inbound  -> qty = +inbound_qty
    - outbound -> qty = -outbound_qty
    - void     -> qty = -void_qty
    """
    if df is None or df.empty:
        return df

    df2 = df.copy()
    if "qty" not in df2.columns:
        df2["qty"] = 0

    if "type" in df2.columns:
        inbound_mask = df2["type"].eq("inbound")
        outbound_mask = df2["type"].eq("outbound")
        void_mask = df2["type"].eq("void")
    else:
        inbound_mask = outbound_mask = void_mask = False

    if "inbound_qty" in df2.columns:
        df2.loc[inbound_mask, "qty"] = pd.to_numeric(
            df2.loc[inbound_mask, "inbound_qty"], errors="coerce"
        ).fillna(0)
    if "outbound_qty" in df2.columns:
        df2.loc[outbound_mask, "qty"] = -pd.to_numeric(
            df2.loc[outbound_mask, "outbound_qty"], errors="coerce"
        ).fillna(0)
    if "void_qty" in df2.columns:
        df2.loc[void_mask, "qty"] = -pd.to_numeric(
            df2.loc[void_mask, "void_qty"], errors="coerce"
        ).fillna(0)

    try:
        df2["qty"] = df2["qty"].astype(int)
    except Exception:
        pass

    return df2


def _apply_filters(df: pd.DataFrame, locations_col) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    with st.container(border=True):
        st.caption("Filters")

        c1, c2, c3, c4 = st.columns(4)
        sku_options = sorted(
            [
                s
                for s in df.get("sku", pd.Series(dtype=str))
                .dropna()
                .astype(str)
                .str.strip()
                .str.upper()
                .unique()
                if s
            ]
        )
        selected_skus = c1.multiselect(
            "SKU",
            options=sku_options,
            default=[],
            help="Search and select one or more SKUs (dropdown items are checkable). Leave empty to include all SKUs.",
        )
        product_name = c2.text_input("Product name contains", value="").strip().upper()
        shipment_id = c3.text_input("Shipment ID contains", value="").strip().upper()
        
        # Get active locations from database
        location_options = []
        try:
            locs = list(
                locations_col.find({"active": True}, {"_id": 0, "location": 1}).sort(
                    "location", 1
                )
            )
            location_options = sorted([str(d.get("location", "")).strip().upper() for d in locs if d.get("location")])
        except Exception:
            pass
        
        selected_locations = c4.multiselect(
            "Locations",
            options=location_options,
            default=[],
            help="Search and select one or more Locations (dropdown items are checkable). Leave empty to include all Locations.",
        )

        c5, c6, c7 = st.columns([1, 1, 1])
        type_opt = c5.multiselect(
            "Type",
            options=sorted([t for t in df.get("type", pd.Series(dtype=str)).dropna().unique()]),
            default=sorted([t for t in df.get("type", pd.Series(dtype=str)).dropna().unique()]),
        )

        show_dupes_only = c6.checkbox(
            "Only duplicated Shipment IDs",
            value=False,
            help="Show only rows where shipment_id appears more than once (ignores blank shipment_id).",
        )

        show_fba_only = c7.checkbox(
            "FBA (Amazon) Transactions Only",
            value=False,
            help="Show only transactions to or from location AMAZON.",
        )


        # Date range
        ts = pd.to_datetime(df["timestamp"], errors="coerce") if "timestamp" in df.columns else None
        if ts is not None and ts.notna().any():
            min_date = ts.min().date()
        else:
            min_date = datetime.now().date()

        # Per requirement: end date defaults to current date
        max_date = datetime.now().date()

        d1, d2, _ = st.columns([1, 1, 2])
        start_date = d1.date_input("Start date", value=min_date)
        end_date = d2.date_input("End date", value=max_date)

    out = df.copy()

    def _contains(col: str, val: str) -> None:
        nonlocal out
        if not val or col not in out.columns:
            return
        out[col] = out[col].astype(str)
        out = out[out[col].str.upper().str.contains(val, na=False)]

    if selected_skus and "sku" in out.columns:
        out["sku"] = out["sku"].astype(str).str.strip().str.upper()
        out = out[out["sku"].isin([s.strip().upper() for s in selected_skus if s])]
    _contains("product_name", product_name)
    _contains("shipment_id", shipment_id)
    
    if selected_locations and "location" in out.columns:
        out["location"] = out["location"].astype(str).str.strip().str.upper()
        out = out[out["location"].isin([s.strip().upper() for s in selected_locations if s])]

    if type_opt and "type" in out.columns:
        out = out[out["type"].isin(type_opt)]

    if "timestamp" in out.columns:
        ts2 = pd.to_datetime(out["timestamp"], errors="coerce")
        # Inclusive date filtering
        out = out[ts2.dt.date.between(start_date, end_date)]

    if show_dupes_only and "shipment_id" in out.columns:
        ship = out["shipment_id"].astype(str).str.strip().str.upper()
        non_blank = ship.ne("")
        dupes = ship[non_blank].duplicated(keep=False)
        # Build a boolean mask aligned to `out`
        mask = non_blank & dupes.reindex(out.index, fill_value=False)
        out = out[mask]

    if show_fba_only:
        amazon = "AMAZON"
        masks = []
        if "location" in out.columns:
            out["location"] = out["location"].astype(str).str.strip().str.upper()
            masks.append(out["location"].eq(amazon))
        if "location_from" in out.columns:
            out["location_from"] = (
                out["location_from"].astype(str).str.strip().str.upper()
            )
            masks.append(out["location_from"].eq(amazon))
        if "location_to" in out.columns:
            out["location_to"] = out["location_to"].astype(str).str.strip().str.upper()
            masks.append(out["location_to"].eq(amazon))
        if masks:
            out = out[pd.concat(masks, axis=1).any(axis=1)]

        if "reason" in out.columns:
            out["reason"] = out["reason"].astype(str).str.strip().str.upper()
            reason_is_in = out["reason"].eq("STO TRANSFER IN")
            reason_is_out = out["reason"].eq("STO TRANSFER OUT")
            if "location_from" in out.columns:
                location_from_is_amazon = out["location_from"].eq(amazon)
            else:
                location_from_is_amazon = False
            out = out[(reason_is_in & ~location_from_is_amazon) | (reason_is_out & location_from_is_amazon)]

    return out



def render(*, inventory_col, transactions_col, mm_col, locations_col) -> None:
    st.title("Transactions")

    # Pull transactions from DB (no projection so we don't accidentally omit fields)
    # and sort newest-first at the DB level.
    tx_list = list(transactions_col.find({}).sort("timestamp", -1))
    if not tx_list:
        st.info("No transactions found.")
        return

    df = pd.DataFrame(tx_list)

    # Filter out transactions for deactivated SKUs
    # Get list of active SKUs from MM collection
    active_skus = set()
    for mm_doc in mm_col.find({}, {"_id": 0, "sku": 1, "active": 1}):
        sku = str(mm_doc.get("sku", "")).strip().upper()
        active = mm_doc.get("active", True)  # Default to True for backward compatibility
        if active and sku:
            active_skus.add(sku)

    # Filter transactions to only include active SKUs
    if "sku" in df.columns and active_skus:
        df["sku"] = df["sku"].astype(str).str.strip().str.upper()
        df = df[df["sku"].isin(active_skus)]

    if df.empty:
        st.info("No transactions found for active SKUs.")
        return

    # Ensure expected columns exist (some transaction types won't have shipment_id etc.)
    desired_cols = [
        "timestamp",
        "sku",
        "product_name",
        "shipment_id",
        "location",
        "type",
        "reason",
        "sto",
        "location_from",
        "location_to",
        "qty",
    ]
    for c in desired_cols:
        if c not in df.columns:
            df[c] = "" if c != "qty" else 0

    # Best-effort: fill product name from transaction, else from inventory mapping.
    # Inbound historically didn't write `product_name` into the transaction.
    # Prefer the name stored on each transaction (after the outbound fix).
    # Fallback to inventory name if missing.
    inv_map = {
        (str(d.get("sku", "")).strip().upper(), str(d.get("location", "")).strip().upper()): str(
            d.get("product_name", "")
        ).strip().upper()
        for d in inventory_col.find(
            {},
            {"_id": 0, "sku": 1, "location": 1, "product_name": 1},
        )
    }
    if "sku" in df.columns:
        df["sku"] = df["sku"].astype(str).str.strip().str.upper()
    if "location" in df.columns:
        df["location"] = df["location"].astype(str).str.strip().str.upper()

    # Only fill missing/blank product names.
    df["product_name"] = df["product_name"].astype(str).fillna("")
    missing_product_name = df["product_name"].str.strip().eq("")
    if missing_product_name.any() and "location" in df.columns and "sku" in df.columns:
        df.loc[missing_product_name, "product_name"] = df.loc[missing_product_name].apply(
            lambda r: inv_map.get((r.get("sku"), r.get("location")), ""),
            axis=1,
        )

    df = _compute_qty(df)

    # Convert UTC timestamps to US Central Time
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        # Apply timezone conversion
        df["timestamp"] = df["timestamp"].apply(utc_to_central)

    # Select and order required columns.
    df = df[desired_cols]

    df_filtered = _apply_filters(df, locations_col)

    # Shipment ID Record Button and Display
    if st.button("📋 Shipment ID Record", help="Extract USPS tracking numbers from outbound transactions"):
        # Filter for outbound type and non-empty shipment_id
        outbound_df = df_filtered[
            (df_filtered["type"] == "outbound") & 
            (df_filtered["shipment_id"].notna()) & 
            (df_filtered["shipment_id"].astype(str).str.strip() != "")
        ].copy()
        
        if not outbound_df.empty:
            # Extract and clean shipment IDs using proper USPS validation
            shipment_ids = []
            
            for sid in outbound_df["shipment_id"].unique():
                cleaned = str(sid).strip().upper()
                # Extract valid USPS tracking numbers from the shipment_id text
                extracted = _extract_tracking_numbers_from_text(cleaned)
                for tracking in extracted:
                    if tracking not in shipment_ids:  # Avoid duplicates
                        shipment_ids.append(tracking)
            
            if shipment_ids:
                # Initialize session state for pagination
                if "shipment_page" not in st.session_state:
                    st.session_state.shipment_page = 0
                
                # Pagination settings
                items_per_page = 25
                total_pages = (len(shipment_ids) + items_per_page - 1) // items_per_page
                current_page = st.session_state.shipment_page
                
                # Get current page items
                start_idx = current_page * items_per_page
                end_idx = min(start_idx + items_per_page, len(shipment_ids))
                current_items = shipment_ids[start_idx:end_idx]
                
                # Display with comma-separated values
                st.markdown(f"**USPS Tracking Numbers (Page {current_page + 1}/{total_pages})**")
                st.caption(f"Showing {len(current_items)} of {len(shipment_ids)} tracking numbers. Click the copy icon to copy.")
                
                # Format with line breaks for readability (similar to shipment_tracking.py)
                tracking_list = current_items
                wrapped_lines = []
                current_line = []
                current_length = 0
                
                for tracking in tracking_list:
                    # Account for comma if not first item
                    item_length = len(tracking) + (1 if current_line else 0)
                    
                    if current_length + item_length > 90 and current_line:
                        # Start new line
                        wrapped_lines.append(", ".join(current_line) + ",")
                        current_line = [tracking]
                        current_length = len(tracking)
                    else:
                        current_line.append(tracking)
                        current_length += item_length
                
                # Add remaining items
                if current_line:
                    wrapped_lines.append(", ".join(current_line))
                
                wrapped_text = "\n".join(wrapped_lines)
                st.code(wrapped_text, language=None)
                
                # Pagination controls
                if total_pages > 1:
                    col_prev, col_info, col_next = st.columns([1, 2, 1])
                    with col_prev:
                        if current_page > 0:
                            if st.button("⬅️ Previous", key="prev_page"):
                                st.session_state.shipment_page -= 1
                                st.rerun()
                    with col_info:
                        st.caption(f"Page {current_page + 1} of {total_pages} • Total: {len(shipment_ids)} tracking numbers")
                    with col_next:
                        if current_page < total_pages - 1:
                            if st.button("Next ➡️", key="next_page"):
                                st.session_state.shipment_page += 1
                                st.rerun()
            else:
                st.warning("No valid USPS tracking numbers found (must be 22 digits starting with 92, 93, 94, or 95)")
        else:
            st.info("No outbound transactions with shipment IDs found in filtered results")

    # Calculate and display total quantity for filtered items
    total_qty = df_filtered["qty"].sum() if "qty" in df_filtered.columns else 0
    st.metric("Total Quantity (Filtered Transactions)", f"{int(total_qty):,}")

    # Display timestamp as string for the final table.
    df_display = df_filtered.copy()
    if "timestamp" in df_display.columns:
        df_display["timestamp"] = df_display["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    st.caption(f"Showing {len(df_display):,} of {len(df):,} transactions")
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "product_name": st.column_config.TextColumn("Product Name"),
        },
    )
