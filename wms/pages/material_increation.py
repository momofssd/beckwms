from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st


def render(*, mm_col) -> None:
    """Material master maintenance.

    Creates/updates material master records in collection `MM`.
    Document shape:
      { sku: str, name: str, created_at: datetime, updated_at: datetime }
    """

    st.title("Material Creation")
    st.caption("Create materials (master data). Inbound requires SKU to exist here.")

    with st.form("mm_create", clear_on_submit=True):
        c1, c2 = st.columns(2)
        sku = c1.text_input("SKU", help="Will be saved uppercased and trimmed.")
        name = c2.text_input(
            "Product Name", help="Will be saved uppercased and trimmed."
        )

        if st.form_submit_button("Create Material", type="primary"):
            sku_n = (sku or "").strip().upper()
            name_n = (name or "").strip().upper()
            if not sku_n:
                st.error("SKU is required.")
            elif not name_n:
                st.error("Product Name is required.")
            else:
                now = datetime.now()
                mm_col.update_one(
                    {"sku": sku_n},
                    {
                        "$set": {
                            "sku": sku_n,
                            "product_name": name_n,
                            "updated_at": now,
                        },
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
                st.success(f"Saved material: {sku_n} - {name_n}")
                st.rerun()

    st.divider()
    st.subheader("Material Master (MM)")
    mm_list = list(mm_col.find({}, {"_id": 0}).sort("sku", 1))
    if not mm_list:
        st.info("No materials created yet.")
        return

    df = pd.DataFrame(mm_list)
    # Nice-to-have ordering if timestamps exist
    preferred = [
        c for c in ["sku", "product_name", "created_at", "updated_at"] if c in df.columns
    ]
    st.dataframe(df[preferred] if preferred else df, use_container_width=True, hide_index=True)
