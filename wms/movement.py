from __future__ import annotations

"""Movement collection helpers.

Movement documents represent a *session-level* movement with embedded transaction details.

Outbound:
- transaction_num: 8 digits, starts with '2' (ascending)
Inbound:
- transaction_num: 6 digits, starts with '1' (ascending)
Void:
- transaction_num: 4 digits, starts with '3' (ascending)
"""

from datetime import datetime


def _next_numeric_id(*, movement_col, prefix: str, digits: int) -> str:
    """Return next numeric id with required prefix and total digits.

    This uses a best-effort approach by looking at the max existing value in the DB.
    (If you later need strict concurrency guarantees, we can add a dedicated counters
    collection with find_one_and_update + $inc.)
    """

    # NOTE: We only filter by prefix (string) so there is no shared max-digit
    # range between inbound/outbound/void. Each type can grow without being
    # limited to a fixed numeric ceiling; the *zfill* width is only for display.
    last = movement_col.find_one(
        {"transaction_num": {"$regex": f"^{prefix}"}},
        sort=[("transaction_num", -1)],
        projection={"_id": 0, "transaction_num": 1},
    )

    if last:
        last_num = str(last.get("transaction_num", "")).strip()
        if last_num.startswith(prefix) and last_num[len(prefix) :].isdigit():
            nxt_int = int(last_num) + 1
            return str(nxt_int).zfill(max(digits, len(str(nxt_int))))

    # Start number
    start_int = int(prefix + "0" * (digits - 1))
    return str(start_int).zfill(digits)


def next_outbound_transaction_num(*, movement_col) -> str:
    return _next_numeric_id(movement_col=movement_col, prefix="2", digits=8)


def next_inbound_transaction_num(*, movement_col) -> str:
    return _next_numeric_id(movement_col=movement_col, prefix="1", digits=6)


def next_void_transaction_num(*, movement_col) -> str:
    # 3 + 3 digits, starting at 3001
    return _next_numeric_id(movement_col=movement_col, prefix="3", digits=4)


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
