from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st


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


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
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
        location = c4.text_input("Location contains", value="").strip().upper()

        c5, c6, _ = st.columns([1, 1, 2])
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
    _contains("location", location)

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

    return out


def render(*, inventory_col, transactions_col) -> None:
    st.title("Transactions")

    # Pull transactions from DB (no projection so we don't accidentally omit fields)
    # and sort newest-first at the DB level.
    tx_list = list(transactions_col.find({}).sort("timestamp", -1))
    if not tx_list:
        st.info("No transactions found.")
        return

    df = pd.DataFrame(tx_list)

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

    # Standardize timestamp display (keep sortable datetime for filtering).
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Select and order required columns.
    df = df[desired_cols]

    df_filtered = _apply_filters(df)

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
