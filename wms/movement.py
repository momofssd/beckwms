from __future__ import annotations

"""Movement collection helpers.

Movement documents represent a *session-level* movement with embedded transaction details.

Outbound:
- transaction_num: 8 digits, starts with '2' (ascending)
Inbound:
- transaction_num: 6 digits, starts with '1' (ascending)
"""

from datetime import datetime


def _next_numeric_id(*, movement_col, prefix: str, digits: int) -> str:
    """Return next numeric id with required prefix and total digits.

    This uses a best-effort approach by looking at the max existing value in the DB.
    (If you later need strict concurrency guarantees, we can add a dedicated counters
    collection with find_one_and_update + $inc.)
    """

    lo = int(prefix + "0" * (digits - 1))
    hi = int(prefix + "9" * (digits - 1))

    last = movement_col.find_one(
        {"transaction_num": {"$gte": str(lo), "$lte": str(hi)}},
        sort=[("transaction_num", -1)],
        projection={"_id": 0, "transaction_num": 1},
    )

    if last and str(last.get("transaction_num", "")).isdigit():
        nxt = int(last["transaction_num"]) + 1
    else:
        nxt = lo

    return str(nxt).zfill(digits)


def next_outbound_transaction_num(*, movement_col) -> str:
    return _next_numeric_id(movement_col=movement_col, prefix="2", digits=8)


def next_inbound_transaction_num(*, movement_col) -> str:
    return _next_numeric_id(movement_col=movement_col, prefix="1", digits=6)


def build_movement_doc(
    *,
    movement_type: str,
    transaction_num: str,
    qty: int,
    location: str,
    details: list[dict],
) -> dict:
    """Create the document for the movement collection."""

    return {
        "timestamp": datetime.now(),
        "movement_type": str(movement_type).strip().lower(),
        "transaction_num": str(transaction_num),
        "qty": int(qty),
        "location": str(location).strip().upper(),
        "details": details,
    }

