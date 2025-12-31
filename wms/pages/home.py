import pandas as pd
import streamlit as st
from datetime import datetime


def render(*, inventory_col, transactions_col) -> None:
    st.title("Inventory Management")
    raw_data = list(inventory_col.find())
    if not raw_data:
        return

    df_display = pd.DataFrame(raw_data)
    if st.session_state.user_role == "admin":
        st.subheader("Inventory Editor (Admin Only)")
        st.data_editor(
            df_display,
            column_config={"_id": None},
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
                    transactions_col.insert_one(
                        {
                            "timestamp": datetime.now(),
                            "sku": str(row.get("sku", "")).strip().upper(),
                            "location": str(row.get("location", "")).strip().upper(),
                            "type": "void",
                            "void_qty": int(current_qty),
                            "reason": "Inventory Editor delete -> void to zero",
                        }
                    )
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
                    transactions_col.insert_one(
                        {
                            "timestamp": datetime.now(),
                            "sku": str(current_row.get("sku", "")).strip().upper(),
                            "location": str(current_row.get("location", "")).strip().upper(),
                            "type": "void",
                            "void_qty": int(reduced_by),
                            "reason": "Inventory Editor quantity reduction",
                        }
                    )

                updated_values = {
                    "sku": str(changes.get("sku", current_row["sku"])).strip().upper(),
                    "name": str(changes.get("name", current_row["name"])).strip().upper(),
                    "location": str(changes.get("location", current_row["location"])).strip().upper(),
                    "quantity": int(new_qty),
                }
                inventory_col.update_one({"_id": doc_id}, {"$set": updated_values})

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
