from datetime import datetime

import pandas as pd
import streamlit as st

from wms.movement import build_movement_doc, next_inbound_transaction_num
from wms.ui_utils import auto_focus_aria_label_js


def _get_location_options(locations_col) -> list[str]:
    """Return active locations for dropdown selection."""
    try:
        locs = list(
            locations_col.find({"active": True}, {"_id": 0, "location": 1}).sort(
                "location", 1
            )
        )
        opts = [str(d.get("location", "")).strip().upper() for d in locs]
        return [o for o in opts if o]
    except Exception:
        # Fail safe: if Locations collection is missing/misconfigured.
        return []


def _get_sku_options(mm_col) -> list[str]:
    """Return SKU options from Material Master (MM)."""
    try:
        skus = list(mm_col.find({}, {"_id": 0, "sku": 1}).sort("sku", 1))
        opts = [str(d.get("sku", "")).strip().upper() for d in skus]
        return [o for o in opts if o]
    except Exception:
        return []


def render(*, inventory_col, transactions_col, mm_col, locations_col, movement_col) -> None:
    st.title("Inbound Entry")

    tab_inbound, tab_manual = st.tabs(["Inbound Entry", "Manual Inbound Entry"])

    def _go_to_scan_step_2() -> None:
        """Advance the scan flow to step 2 when the user presses Enter."""
        scanned_local = (st.session_state.get("inbound_scan_sku_input") or "").strip().upper()
        if scanned_local:
            st.session_state.inbound_scanned_sku = scanned_local
            st.session_state.inbound_scan_step = 2

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
                    loc2 = c1.selectbox(
                        "Location",
                        options=location_options,
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
                        {"_id": 0, "sku": 1, "product_name": 1, "name": 1},
                    )
                    if not mm_doc:
                        st.error(
                            f"SKU {sku2} is not registered in Material Master (MM). "
                            "Please create it first under Master Data."
                        )
                        return

                    if not loc2:
                        st.error("Location is required.")
                        return

                    name2 = str(
                        mm_doc.get("product_name") or mm_doc.get("name") or ""
                    ).strip().upper()
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
                        }
                    )

                    # Movement logging
                    # NOTE: If this fails, we still want the inbound itself to succeed,
                    # but we should surface the error so it can be fixed (otherwise
                    # transaction_num will appear "stuck").
                    try:
                        txn_num = next_inbound_transaction_num(movement_col=movement_col)
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
                                }
                            ],
                        )
                        movement_col.insert_one(mv)
                    except Exception as e:
                        st.warning(
                            "Inbound succeeded, but Movement logging failed. "
                            f"(transaction_num may not increment) Error: {e}"
                        )

                    # Reset scan flow back to step 1 for the next item.
                    st.session_state.inbound_scan_step = 1
                    st.session_state.inbound_scanned_sku = ""
                    st.session_state.inbound_scan_sku_input = ""
                    st.success(f"Inbound Successful: {qty2} units of {sku2}")
                    st.rerun()

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
                loc = c2.selectbox("Location", options=location_options)
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
                            }
                        )

                        # Movement logging
                        try:
                            txn_num = next_inbound_transaction_num(
                                movement_col=movement_col
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
                                    }
                                ],
                            )
                            movement_col.insert_one(mv)
                        except Exception as e:
                            st.warning(
                                "Entry succeeded, but Movement logging failed. "
                                f"(transaction_num may not increment) Error: {e}"
                            )
                        st.success(f"Entry Successful: {qty} units of {sku_n}")
                        st.rerun()

    st.divider()
    st.subheader("Current Inventory Status")
    inventory_data = list(inventory_col.find({}, {"_id": 0}))
    if inventory_data:
        st.dataframe(pd.DataFrame(inventory_data), use_container_width=True)
