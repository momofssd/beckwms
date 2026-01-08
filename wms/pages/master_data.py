from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st


def render(*, mm_col, locations_col) -> None:
    """Master Data maintenance.

    Currently supports:
      - Materials (MM collection)
      - Locations (Locations collection)
    """

    st.title("Master Data")

    tab_mm, tab_loc = st.tabs(["Materials", "Locations"])

    with tab_mm:
        st.subheader("Materials (MM)")
        st.caption("Inbound requires SKU to exist here.")

        is_admin = (st.session_state.get("user_role") or "").strip().lower() == "admin"
        if not is_admin:
            st.info("Only Admin users can edit SKU active status.")

        with st.form("mm_create", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 2, 1])
            sku = c1.text_input("SKU", help="Will be saved uppercased and trimmed.")
            name = c2.text_input(
                "Product Name", help="Will be saved uppercased and trimmed."
            )
            active = c3.checkbox("Active", value=True)

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
                                "active": bool(active),
                                "updated_at": now,
                            },
                            "$setOnInsert": {"created_at": now},
                        },
                        upsert=True,
                    )
                    st.success(f"Saved material: {sku_n} - {name_n}")
                    st.rerun()

        mm_list = list(mm_col.find({}, {"_id": 0}).sort("sku", 1))
        if not mm_list:
            st.info("No materials created yet.")
        else:
            df = pd.DataFrame(mm_list)
            
            # Ensure 'active' column exists with default True for backward compatibility
            if "active" not in df.columns:
                df["active"] = True
            else:
                # Fill any missing/null values with True
                df["active"] = df["active"].fillna(True)
            
            # Convert to boolean to ensure proper checkbox rendering
            df["active"] = df["active"].astype(bool)
            
            # Sort by active status (active first) then by SKU
            df = df.sort_values(by=["active", "sku"], ascending=[False, True])
            
            preferred = [
                c
                for c in ["sku", "product_name", "active", "created_at", "updated_at"]
                if c in df.columns
            ]
            df_view = df[preferred] if preferred else df

            # Inline editing for Admins: allow toggling Active directly in the table.
            edited = st.data_editor(
                df_view,
                use_container_width=True,
                hide_index=True,
                disabled=(not is_admin),
                column_config={
                    "active": st.column_config.CheckboxColumn(
                        "Active",
                        help="Admin can enable/disable a SKU.",
                    )
                },
                key="mm_editor",
            )

            if st.button("Save Material Changes", type="primary", disabled=(not is_admin)):
                # Compare original vs edited to find changes.
                merged = df_view.merge(
                    edited[["sku", "active"]],
                    on="sku",
                    how="left",
                    suffixes=("_old", "_new"),
                )
                changes = merged[
                    merged["active_old"].astype(bool) != merged["active_new"].astype(bool)
                ]

                if changes.empty:
                    st.info("No changes to save.")
                else:
                    now = datetime.now()
                    for _, r in changes.iterrows():
                        mm_col.update_one(
                            {"sku": str(r["sku"]).strip().upper()},
                            {"$set": {"active": bool(r["active_new"]), "updated_at": now}},
                            upsert=False,
                        )
                    st.success(f"Saved {len(changes)} change(s).")
                    st.rerun()

    with tab_loc:
        st.subheader("Locations")
        st.caption("Used for inbound/outbound location selection.")

        is_admin = (st.session_state.get("user_role") or "").strip().lower() == "admin"
        if not is_admin:
            st.info("Only Admin users can edit Location active status.")

        with st.form("location_create", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            loc = c1.text_input(
                "Location",
                help="Will be saved uppercased and trimmed (e.g., A01, RACK-1).",
            )
            active = c2.checkbox("Active", value=True)

            if st.form_submit_button("Create Location", type="primary"):
                loc_n = (loc or "").strip().upper()
                if not loc_n:
                    st.error("Location is required.")
                else:
                    now = datetime.now()
                    # Unique by location name.
                    locations_col.update_one(
                        {"location": loc_n},
                        {
                            "$set": {
                                "location": loc_n,
                                "active": bool(active),
                                "updated_at": now,
                            },
                            "$setOnInsert": {"created_at": now},
                        },
                        upsert=True,
                    )
                    st.success(f"Saved location: {loc_n}")
                    st.rerun()

        loc_list = list(
            locations_col.find({}, {"_id": 0}).sort([("active", -1), ("location", 1)])
        )
        if not loc_list:
            st.info("No locations created yet.")
        else:
            df = pd.DataFrame(loc_list)
            preferred = [
                c for c in ["location", "active", "created_at", "updated_at"] if c in df.columns
            ]
            df_view = df[preferred] if preferred else df

            # Inline editing for Admins: allow toggling Active directly in the table.
            edited = st.data_editor(
                df_view,
                use_container_width=True,
                hide_index=True,
                disabled=(not is_admin),
                column_config={
                    "active": st.column_config.CheckboxColumn(
                        "Active",
                        help="Admin can enable/disable a location.",
                    )
                },
                key="locations_editor",
            )

            if st.button("Save Location Changes", type="primary", disabled=(not is_admin)):
                # Compare original vs edited to find changes.
                merged = df_view.merge(
                    edited[["location", "active"]],
                    on="location",
                    how="left",
                    suffixes=("_old", "_new"),
                )
                changes = merged[
                    merged["active_old"].astype(bool) != merged["active_new"].astype(bool)
                ]

                if changes.empty:
                    st.info("No changes to save.")
                else:
                    now = datetime.now()
                    for _, r in changes.iterrows():
                        locations_col.update_one(
                            {"location": str(r["location"]).strip().upper()},
                            {"$set": {"active": bool(r["active_new"]), "updated_at": now}},
                            upsert=False,
                        )
                    st.success(f"Saved {len(changes)} change(s).")
                    st.rerun()
