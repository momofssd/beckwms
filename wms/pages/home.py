import pandas as pd
import streamlit as st


def render(*, inventory_col) -> None:
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
            for row_idx in state.get("deleted_rows", []):
                inventory_col.delete_one({"_id": df_display.iloc[row_idx]["_id"]})

            for row_idx_str, changes in state.get("edited_rows", {}).items():
                row_idx = int(row_idx_str)
                doc_id = df_display.iloc[row_idx]["_id"]
                current_row = df_display.iloc[row_idx].to_dict()
                updated_values = {
                    "sku": str(changes.get("sku", current_row["sku"])).strip().upper(),
                    "name": str(changes.get("name", current_row["name"])).strip().upper(),
                    "location": str(changes.get("location", current_row["location"])).strip().upper(),
                    "quantity": int(changes.get("quantity", current_row["quantity"]))
                }
                inventory_col.update_one({"_id": doc_id}, {"$set": updated_values})

            for row in state.get("added_rows", []):
                inventory_col.insert_one(
                    {
                        "sku": row.get("sku", "").upper(),
                        "name": row.get("name", "").upper(),
                        "location": row.get("location", "").upper(),
                        "quantity": int(row.get("quantity", 0)),
                    }
                )

            st.success("Database synchronized.")
            st.rerun()
    else:
        st.subheader("Stock Levels (View Only)")
        st.dataframe(df_display.drop(columns=["_id"]), use_container_width=True)

