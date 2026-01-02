from __future__ import annotations

import json

import pandas as pd
import streamlit as st


def render(*, movement_col) -> None:
    st.title("Movements")
    st.caption("Session-level movement documents (inbound/outbound/void)")

    mv_list = list(movement_col.find({}).sort("timestamp", -1))
    if not mv_list:
        st.info("No movement records found.")
        return

    df = pd.DataFrame(mv_list)
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])

    # Normalize timestamp for display
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

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

    df_filtered = df.copy()
    if "timestamp" in df_filtered.columns:
        ts = pd.to_datetime(df_filtered["timestamp"], errors="coerce")
        df_filtered = df_filtered[ts.dt.date.between(start_date, end_date)]
    if selected_types and "movement_type" in df_filtered.columns:
        df_filtered = df_filtered[
            df_filtered["movement_type"].astype(str).str.lower().isin(selected_types)
        ]

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

    cols = [
        c
        for c in [
            "timestamp",
            "movement_type",
            "transaction_num",
            "qty",
            "location",
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

    st.dataframe(
        df_filtered[cols + extra_cols],
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

    # Look up the selected movement from the *unfiltered* list so details still work
    # even if the user changes filters after copying a transaction number.
    selected_mv = next(
        (mv for mv in mv_list if str(mv.get("transaction_num", "")) == selected_txn),
        None,
    )
    if not selected_mv:
        st.warning(f"No movement found for transaction_num={selected_txn}")
        return

    details = (selected_mv or {}).get("details") or []
    if not isinstance(details, list) or len(details) == 0:
        st.caption("No details")
        return

    # Deconstruct (normalize) the embedded details objects into a table.
    # This will expand nested keys and keep columns consistent.
    try:
        df_details = pd.json_normalize(details)
        # nicer timestamp rendering
        if "timestamp" in df_details.columns:
            df_details["timestamp"] = pd.to_datetime(
                df_details["timestamp"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_details, use_container_width=True, hide_index=True)
    except Exception:
        st.code(json.dumps(details, default=str, indent=2), language="json")
