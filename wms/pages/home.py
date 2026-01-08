import pandas as pd
import streamlit as st
from datetime import datetime

from wms.movement import build_movement_doc, next_void_transaction_num


def render(*, inventory_col, transactions_col, movement_col) -> None:
    st.title("Inventory Management")
    
    # Import mm_col to check active status
    from wms.db import get_collections
    cols = get_collections()
    mm_col = cols["mm"]
    
    raw_data = list(inventory_col.find())
    if not raw_data:
        return

    df_display = pd.DataFrame(raw_data)
    
    # Filter out rows with quantity <= 0
    df_display = df_display[df_display["quantity"] > 0]
    
    # Filter to only show items whose SKU is active
    if "sku" in df_display.columns and not df_display.empty:
        # Get active SKUs from MM collection
        active_skus = set()
        for mm_doc in mm_col.find({}, {"_id": 0, "sku": 1, "active": 1}):
            sku = str(mm_doc.get("sku", "")).strip().upper()
            active = mm_doc.get("active", True)  # Default to True for backward compatibility
            if active and sku:
                active_skus.add(sku)
        
        # Filter inventory to only include active SKUs
        if active_skus:
            df_display["sku"] = df_display["sku"].astype(str).str.strip().str.upper()
            df_display = df_display[df_display["sku"].isin(active_skus)]
    
    if df_display.empty:
        st.info("No inventory items with quantity greater than 0.")
        return
    
    # Add filters for location and SKU with multi-select
    st.subheader("Filters")
    col1, col2 = st.columns(2)
    
    with col1:
        all_locations = sorted(df_display["location"].unique().tolist())
        selected_locations = st.multiselect(
            "Filter by Location",
            options=all_locations,
            default=all_locations,
            key="location_filter"
        )
    
    with col2:
        all_skus = sorted(df_display["sku"].unique().tolist())
        selected_skus = st.multiselect(
            "Filter by SKU",
            options=all_skus,
            default=all_skus,
            key="sku_filter"
        )
    
    # Apply filters
    if selected_locations:
        df_display = df_display[df_display["location"].isin(selected_locations)]
    else:
        df_display = pd.DataFrame(columns=df_display.columns)
    
    if selected_skus:
        df_display = df_display[df_display["sku"].isin(selected_skus)]
    else:
        df_display = pd.DataFrame(columns=df_display.columns)
    
    if df_display.empty:
        st.info("No inventory items match the selected filters.")
        return
    
    # Calculate and display total quantity for rendered items
    total_qty = df_display["quantity"].sum() if "quantity" in df_display.columns else 0
    st.metric("Total Quantity (Filtered Items)", f"{int(total_qty):,}")
    
    if st.session_state.user_role == "admin":
        st.subheader("Inventory Editor (Admin Only)")
        st.data_editor(
            df_display,
            # Hide Mongo internal id; only allow editing quantity.
            column_config={
                "_id": None,
                "sku": st.column_config.TextColumn("SKU", disabled=True),
                "product_name": st.column_config.TextColumn("Product Name", disabled=True),
                "location": st.column_config.TextColumn("Location", disabled=True),
                "quantity": st.column_config.NumberColumn(
                    "Quantity",
                    min_value=0,
                    step=1,
                    help="Admin can only reduce quantity here. Use Inbound Entry to increase."
                ),
            },
            num_rows="dynamic",
            use_container_width=True,
            key="inventory_table",
        )
        if st.button("Apply Changes and Sync Database", type="primary"):
            state = st.session_state.inventory_table

            # --- Handle deletions as VOID (do not remove records; set qty to 0 and log transaction) ---
            for row_idx in state.get("deleted_rows", []):
                row = df_display.iloc[row_idx].to_dict()
                current_qty = int(row.get("quantity", 0) or 0)
                if current_qty > 0:
                    tx_doc = {
                        "timestamp": datetime.now(),
                        "sku": str(row.get("sku", "")).strip().upper(),
                        "product_name": str(row.get("product_name", "")).strip().upper(),
                        "location": str(row.get("location", "")).strip().upper(),
                        "type": "void",
                        "void_qty": int(current_qty),
                        "reason": "Inventory Editor delete -> void to zero",
                    }
                    transactions_col.insert_one(
                        tx_doc
                    )

                    # Movement doc (void)
                    try:
                        txn_num = next_void_transaction_num(movement_col=movement_col)
                        mv = build_movement_doc(
                            movement_type="void",
                            transaction_num=txn_num,
                            qty=int(current_qty),
                            location=str(row.get("location", "")).strip().upper(),
                            details=[tx_doc],
                        )
                        movement_col.insert_one(mv)
                    except Exception:
                        # Do not block inventory edits on movement failures.
                        pass
                inventory_col.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"quantity": 0}},
                )

            for row_idx_str, changes in state.get("edited_rows", {}).items():
                row_idx = int(row_idx_str)
                doc_id = df_display.iloc[row_idx]["_id"]
                current_row = df_display.iloc[row_idx].to_dict()

                old_qty = int(current_row.get("quantity", 0) or 0)
                new_qty = int(changes.get("quantity", old_qty) or 0)

                # Only allow reducing qty from the editor; increases are blocked.
                if new_qty > old_qty:
                    st.error(
                        f"Not allowed: increasing quantity in Inventory Editor ({current_row.get('sku')} at {current_row.get('location')}). "
                        "Use Inbound Entry instead."
                    )
                    new_qty = old_qty

                # If qty was reduced, log it as a VOID transaction (audit trail).
                reduced_by = old_qty - new_qty
                if reduced_by > 0:
                    tx_doc = {
                        "timestamp": datetime.now(),
                        "sku": str(current_row.get("sku", "")).strip().upper(),
                        "product_name": str(current_row.get("product_name", "")).strip().upper(),
                        "location": str(current_row.get("location", "")).strip().upper(),
                        "type": "void",
                        "void_qty": int(reduced_by),
                        "reason": "Inventory Editor quantity reduction",
                    }
                    transactions_col.insert_one(
                        tx_doc
                    )

                    # Movement doc (void)
                    try:
                        txn_num = next_void_transaction_num(movement_col=movement_col)
                        mv = build_movement_doc(
                            movement_type="void",
                            transaction_num=txn_num,
                            qty=int(reduced_by),
                            location=str(current_row.get("location", "")).strip().upper(),
                            details=[tx_doc],
                        )
                        movement_col.insert_one(mv)
                    except Exception:
                        # Do not block inventory edits on movement failures.
                        pass

                # Only sync quantity changes. sku/location/product_name are not editable.
                inventory_col.update_one({"_id": doc_id}, {"$set": {"quantity": int(new_qty)}})

            # Disallow adding rows from the editor to avoid untracked inventory creation.
            if state.get("added_rows"):
                st.error(
                    "Not allowed: adding new inventory rows from Inventory Editor. Use Inbound Entry instead."
                )

            st.success("Database synchronized.")
            st.rerun()
    else:
        st.subheader("Stock Levels (View Only)")
        st.dataframe(df_display.drop(columns=["_id"]), use_container_width=True)
