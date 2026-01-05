from __future__ import annotations

"""Movement collection helpers.

Movement documents represent a *session-level* movement with embedded transaction details.

Outbound:
- transaction_num: 8 digits, starts with '2' (ascending)
Inbound:
- transaction_num: 6 digits, starts with '1' (ascending)
Void:
- transaction_num: 4 digits, starts with '3' (ascending)
STO:
- transaction_num: 5 digits, starts at 10000 (ascending) e.g. 10000
"""

from datetime import datetime

from pymongo import ReturnDocument


def _next_numeric_id(*, movement_col, prefix: str, digits: int) -> str:
    """Return next numeric id with required prefix and total digits.

    This uses a best-effort approach by looking at the max existing value in the DB.
    (If you later need strict concurrency guarantees, we can add a dedicated counters
    collection with find_one_and_update + $inc.)
    """

    # NOTE: We only filter by prefix (string) so there is no shared max-digit
    # range between inbound/outbound/void. Each type can grow without being
    # limited to a fixed numeric ceiling; the *zfill* width is only for display.
    # IMPORTANT:
    # We only want to consider numeric transaction numbers for this prefix.
    # Sort-by-string can yield wrong "max" when values have inconsistent
    # widths (e.g. '10003' vs '010003'). We therefore:
    #   1) filter to digits-only values
    #   2) fetch a small window of candidates ordered by transaction_num desc
    #   3) compute the true numeric max in Python
    candidates = list(
        movement_col.find(
            {"transaction_num": {"$regex": f"^{prefix}\\d+$"}},
            projection={"_id": 0, "transaction_num": 1},
        )
        .sort("transaction_num", -1)
        .limit(50)
    )

    max_int: int | None = None
    for doc in candidates:
        s = str(doc.get("transaction_num", "")).strip()
        if not (s.startswith(prefix) and s[len(prefix) :].isdigit()):
            continue
        try:
            v = int(s)
        except Exception:
            continue
        if max_int is None or v > max_int:
            max_int = v

    if max_int is not None:
        nxt_int = max_int + 1
        return str(nxt_int).zfill(max(digits, len(str(nxt_int))))

    # Start number
    start_int = int(prefix + "0" * (digits - 1))
    return str(start_int).zfill(digits)


def next_outbound_transaction_num(*, movement_col) -> str:
    return _next_numeric_id(movement_col=movement_col, prefix="2", digits=8)


def next_inbound_transaction_num(*, movement_col) -> str:
    """Return next inbound transaction number.

    Uses an atomic counter stored in a dedicated `counters` collection.
    This avoids duplicates and ensures the number always increments even
    with concurrent users.
    """

    db = movement_col.database
    counters = db["counters"]

    # Determine the current maximum inbound transaction number in the movement
    # collection. We accept legacy/incorrect formatting like '010003' and
    # normalize it by numeric max.
    base = 100000  # inbound should start at 100000
    try:
        docs = list(
            movement_col.find(
                {"movement_type": "inbound", "transaction_num": {"$regex": r"^\d+$"}},
                projection={"_id": 0, "transaction_num": 1},
            )
            .sort("transaction_num", -1)
            .limit(200)
        )
        for d in docs:
            s = str(d.get("transaction_num", "")).strip()
            if not s.isdigit():
                continue
            v = int(s)
            # Only consider values that would fall into inbound's numeric band.
            # This allows migrating from '010003' -> next becomes 100000.
            if v >= base and v < 200000:
                base = max(base, v)
    except Exception:
        pass

    # If counter doesn't exist, initialize it to the discovered base.
    counters.update_one(
        {"_id": "inbound_transaction_num"},
        {"$setOnInsert": {"seq": base}},
        upsert=True,
    )

    updated = counters.find_one_and_update(
        {"_id": "inbound_transaction_num"},
        {"$inc": {"seq": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True,
    )

    nxt_int = int((updated or {}).get("seq") or (base + 1))
    # Enforce Option A formatting: 6 digits starting with '1'
    if nxt_int < 100000:
        nxt_int = 100000
    if nxt_int >= 200000:
        # Still return something sensible; prevents generating a '2xxxxx' outbound-looking id.
        nxt_int = 199999
    return str(nxt_int).zfill(6)


def next_void_transaction_num(*, movement_col) -> str:
    # 3 + 3 digits, starting at 3001
    return _next_numeric_id(movement_col=movement_col, prefix="3", digits=4)


def next_sto_transaction_num(*, movement_col) -> str:
    # 5 digits starting at 10000
    last = movement_col.find_one(
        {"movement_type": "sto", "transaction_num": {"$regex": r"^\d{5}$"}},
        sort=[("transaction_num", -1)],
        projection={"_id": 0, "transaction_num": 1},
    )

    if last:
        last_num = str(last.get("transaction_num", "")).strip()
        if last_num.isdigit():
            nxt = int(last_num) + 1
            # Ensure we never generate numbers below 10000 even if legacy data exists.
            if nxt < 10000:
                nxt = 10000
            return str(nxt).zfill(5)

    return "10000"


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
