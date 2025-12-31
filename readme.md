# Beck WMS (Streamlit + MongoDB)

A lightweight Warehouse Management System (WMS) built with **Streamlit** and **MongoDB** (Atlas or self-hosted). It supports:

- Inventory dashboard (view for users, editor for admins)
- Material (SKU) master data creation
- Inbound stock entry (scan flow + manual)
- Outbound scanning terminal (SKU + shipment ID)
- Transaction history with filtering and exports

---

## Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Modules / Pages](#modules--pages)
  - [Inventory Dashboard](#inventory-dashboard)
  - [Material Creation (Material Master)](#material-creation-material-master)
  - [Inbound Entry](#inbound-entry)
  - [Outbound Processing](#outbound-processing)
  - [Transactions](#transactions)
- [Database Schema & Relationships](#database-schema--relationships)
- [Authentication / Roles](#authentication--roles)
- [Exports](#exports)
- [Configuration](#configuration)

---

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Configure MongoDB connection

Set one of the following:

- Environment variable **`MONGO_URI`** (recommended for local dev), or
- Streamlit secret **`mongo_uri`** (recommended for Streamlit Cloud)

Example (Windows cmd):

```bat
set MONGO_URI=mongodb+srv://USER:PASS@cluster.mongodb.net/?retryWrites=true&w=majority
```

### 3) Run the app

```bash
python -m streamlit run app.py
```

---

## Architecture Overview

The app is a **single Streamlit application** with a sidebar-based navigation pattern:

- `app.py` is the Streamlit entrypoint.
- `wms/app.py` wires together:
  - session state initialization
  - authentication
  - MongoDB connections/collections
  - routing to page renderers

### Key packages

- `streamlit` – UI framework
- `pymongo` – MongoDB client
- `pandas` / `openpyxl` – tables + Excel exports
- `python-dotenv` – optional local `.env` loading

---

## Modules / Pages

Navigation is driven by `wms/app.py` via `st.session_state.page`.

### Inventory Dashboard

**File:** `wms/pages/home.py`

**Purpose:** Display current stock by **SKU + location**. Admins can correct data with guardrails.

**How it works**

- Reads all documents from `inventory`.
- **Admin role** (`st.session_state.user_role == "admin"`) gets an editable grid (`st.data_editor`).
- When admin clicks **“Apply Changes and Sync Database”**:
  - **Deletions are treated as VOID**: the record is not removed; instead, `quantity` is set to `0` and a `type="void"` transaction is written.
  - **Edits are applied** with rules:
    - Quantity increases are **blocked** (must use Inbound Entry).
    - Quantity decreases create a `type="void"` transaction for audit.
  - Adding new rows from the editor is **disallowed** (forces inbound flow to create stock).

**Collections used**

- `inventory` (read + update)
- `transactions` (insert audit “void” records)

---

### Material Creation (Material Master)

**File:** `wms/pages/material_increation.py`

**Purpose:** Maintain the **Material Master** (MM): the canonical list of SKUs and product names.

Inbound entry requires a SKU to exist in MM.

**Document shape (MM collection)**

```json
{
  "sku": "ABC123",
  "product_name": "WIDGET",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

**How it works**

- Uses an upsert keyed by `sku`.
- Normalizes `sku` and `product_name` to **trimmed uppercase**.
- Shows a read-only table of all MM records.

**Collections used**

- `MM` (read + upsert)

---

### Inbound Entry

**File:** `wms/pages/inbound.py`

**Purpose:** Add stock into inventory and write an inbound transaction record.

There are two inbound flows:

#### 1) Scan SKU inbound (2-step)

- Step 1: Scan/enter SKU
- Step 2: Enter `quantity` and `location`, then submit

Validations:

- SKU must exist in **Material Master (`MM`)**.
- Location is required.

Writes:

- `inventory` is **upserted** on `(sku, location)` and `quantity` is incremented.
- `transactions` gets a `type="inbound"` record with `inbound_qty`.

#### 2) Manual inbound

- Manually enter SKU, quantity, location
- Same validations and writes as scan flow

**Collections used**

- `MM` (lookup for product name)
- `inventory` (upsert + increment)
- `transactions` (insert)

---

### Outbound Processing

**Files:**

- UI: `wms/pages/outbound.py`
- Scan logic: `wms/outbound.py`

**Purpose:** A scanning terminal to decrement inventory and log outbound shipments.

**How it works (high-level)**

- User selects a **station location** from existing inventory locations.
- Scanning expects a pair of scans:
  1. SKU
  2. Shipment ID (tracking)

When both are scanned, `process_scan()`:

1. **Duplicate shipment protection**

   - If a transaction already exists with the scanned `shipment_id`, it is treated as a replacement.
   - The system adds `+1` back to the previously-shipped inventory line, deletes the old transaction, and removes it from the session log.

2. **Inventory decrement**

   - Attempts to decrement `inventory.quantity` by `1` only if the item is in stock (`quantity > 0`) for the chosen location.

3. **Transaction log**

   - On success, inserts a `type="outbound"` transaction with `outbound_qty = 1`.
   - Also writes a session log entry in memory (`st.session_state.session_log`) for quick exporting.

4. **User feedback**
   - Shows success/error messages and clears the scan input.

The outbound page also includes a “Global Inventory Dashboard” section plus one-click exports.

**Collections used**

- `inventory` (decrement + occasional rollback when replacing a shipment)
- `transactions` (insert/delete)

---

### Transactions

**File:** `wms/pages/transactions.py`

**Purpose:** View, filter, and audit all inventory movements.

**How it works**

- Reads all documents from `transactions` sorted newest-first.
- Normalizes quantity into a signed `qty` column:
  - inbound → `+inbound_qty`
  - outbound → `-outbound_qty`
  - void → `-void_qty`
- Best-effort fills missing `product_name` values from `inventory` (by `(sku, location)` mapping).
- Provides filters:
  - SKU, product name, shipment ID, location
  - Type (multi-select)
  - Date range (inclusive)

**Collections used**

- `transactions` (read)
- `inventory` (optional mapping to fill product names)

---

## Database Schema & Relationships

This app uses **MongoDB** with database name: `warehouse_db`.

Collections are obtained in `wms/db.py`:

- `inventory` – stock by SKU + location
- `MM` – material master (SKU definitions)
- `transactions` – immutable/audit movement log
- `users` – login credentials + role

### 1) `MM` (Material Master)

Canonical SKU registry.

Key fields:

- `sku` (string, uppercase) – **business key**
- `product_name` (string, uppercase)

Recommended index:

- Unique on `sku`

### 2) `inventory`

Represents **current stock position**.

Key fields (typical):

- `sku`
- `product_name`
- `location`
- `quantity` (int)

Business key:

- `(sku, location)` should be unique (application treats it as such via upserts).

Recommended indexes:

- Unique compound index on `(sku, location)`
- Non-unique index on `location` (optional)

Relationship:

- `inventory.sku` → `MM.sku` (many inventory rows can reference one material)

### 3) `transactions`

Append-only movement log (audit trail). The app writes three types:

- `type="inbound"` with `inbound_qty`
- `type="outbound"` with `outbound_qty` and `shipment_id`
- `type="void"` with `void_qty` (admin corrections)

Key fields (varies by type):

- `timestamp` (datetime)
- `sku`
- `product_name` (usually present)
- `location`
- `type` ∈ {inbound, outbound, void}
- `shipment_id` (outbound only)

Recommended indexes:

- Index on `timestamp` (descending)
- Unique (or at least indexed) on `shipment_id` for outbound (the code assumes shipment IDs are unique per outbound)

Relationships:

- `transactions.sku` → `MM.sku`
- `transactions.(sku, location)` → `inventory.(sku, location)` (logical relationship for “which bin changed”)

### 4) `users`

Authentication store.

Key fields:

- `username`
- `password` – SHA-256 hash (see `wms/auth.py`)
- `role` – e.g. `admin` or `user`

Recommended index:

- Unique on `username`

---

## Authentication / Roles

**Files:**

- `wms/auth.py` – login form + SHA-256 hashing
- `wms/session.py` – initializes session defaults

Behavior:

- If `st.session_state.authenticated` is false, the app shows the login form and stops.
- Roles:
  - `admin`: can edit inventory (with safeguards and audit logging)
  - non-admin: view-only inventory dashboard

> Note: user provisioning is handled by writing documents to the `users` collection (no UI in this app).

---

## Exports

The outbound and transactions workflows support Excel exports via `wms/ui_utils.py` (`to_excel`).

- Outbound page exports:
  - current session scans
  - all transactions
  - current inventory snapshot

---

## Configuration

Config resolution is implemented in `wms/config.py`:

Priority order:

1. Environment variables (ex: `MONGO_URI`)
2. Streamlit secrets (ex: `mongo_uri`)

Local `.env` files are supported (best effort) by `wms/app.py` using `python-dotenv`.
