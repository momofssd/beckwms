from datetime import datetime

import pandas as pd
import streamlit as st


def render(*, inventory_col, transactions_col) -> None:
    st.title("Inbound Entry")
    with st.form("inbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        sku = c1.text_input("SKU").upper()
        name = c2.text_input("Product Name").upper()
        qty = c1.number_input("Quantity", min_value=1)
        loc = c2.text_input("Location").upper()
        if st.form_submit_button("Submit Stock Entry", use_container_width=True):
            inventory_col.update_one(
                {"sku": sku, "location": loc},
                {"$set": {"name": name}, "$inc": {"quantity": int(qty)}},
                upsert=True,
            )
            transactions_col.insert_one(
                {
                    "timestamp": datetime.now(),
                    "sku": sku,
                    "location": loc,
                    "type": "inbound",
                    "inbound_qty": int(qty),
                }
            )
            st.success(f"Entry Successful: {qty} units of {sku}")
            st.rerun()

    st.divider()
    st.subheader("Current Inventory Status")
    inventory_data = list(inventory_col.find({}, {"_id": 0}))
    if inventory_data:
        st.dataframe(pd.DataFrame(inventory_data), use_container_width=True)

