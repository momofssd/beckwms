# Beck WMS (Streamlit + MongoDB)

A comprehensive Warehouse Management System (WMS) built with **Streamlit** and **MongoDB** (Atlas or self-hosted). It supports inventory management, material master data, inbound/outbound operations, stock transfers, and complete transaction auditing.

---

## Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [User Interface Pages](#user-interface-pages)
  - [Inventory Dashboard (Home)](#inventory-dashboard-home)
  - [Master Data](#master-data)
  - [Inbound Entry](#inbound-entry)
  - [Outbound Processing](#outbound-processing)
  - [STO - Stock Transfer Order](#sto---stock-transfer-order)
  - [Transactions](#transactions)
  - [Movements](#movements)
- [Database Schema & Structure](#database-schema--structure)
  - [Collections Overview](#collections-overview)
  - [Collection Details](#collection-details)
  - [Relationships](#relationships)
- [Authentication / Roles](#authentication--roles)
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
  - Session state initialization
  - Authentication
  - MongoDB connections/collections
  - Routing to page renderers

### Key packages

- `streamlit` – UI framework
- `pymongo` – MongoDB client
- `pandas` / `openpyxl` – tables + Excel exports
- `python-dotenv` – optional local `.env` loading

### Key modules

- `wms/db.py` – MongoDB connection and collection initialization
- `wms/auth.py` – Login form + SHA-256 password hashing
- `wms/session.py` – Session state initialization
- `wms/movement.py` – Movement document creation and transaction numbering
- `wms/outbound.py` – Outbound scanning logic
- `wms/ui_utils.py` – UI helpers (auto-focus, Excel export, location sorting)
- `wms/timezone_utils.py` – UTC to US Central timezone conversion

---

## User Interface Pages

Navigation is driven by `wms/app.py` via `st.session_state.page`. The sidebar provides buttons to switch between pages.

### Inventory Dashboard (Home)

**File:** `wms/pages/home.py`

**Purpose:** Display and manage current stock levels by SKU and location.

**Functions:**

1. **View Inventory**

   - Displays all inventory items with quantity > 0
   - Filters to show only active SKUs (based on Material Master active status)
   - Multi-select filters for Location and SKU
   - Shows total quantity metric for filtered items

2. **Admin Inventory Editor** (Admin role only)

   - Editable data grid for inventory adjustments
   - **Quantity Reduction:** Admins can reduce quantities (creates void transaction for audit)
   - **Delete Rows:** Treated as VOID - sets quantity to 0 and logs void transaction
   - **Restrictions:**
     - Cannot increase quantity (must use Inbound Entry)
     - Cannot add new rows (must use Inbound Entry)
   - All changes create audit trail in transactions and movement collections

3. **Audit Logging**
   - Every reduction/deletion creates a `type="void"` transaction
   - Movement documents track void operations with transaction numbers (format: 3xxx)

**Collections used:**

- `inventory` (read + update)
- `transactions` (insert void records)
- `movement` (insert void movement documents)
- `MM` (read for active status validation)

---

### Master Data

**File:** `wms/pages/master_data.py`

**Purpose:** Maintain master data for Materials (SKUs) and Locations.

**Functions:**

#### Materials Tab

1. **Create/Update Material**

   - Form to add new SKUs or update existing ones
   - Fields: SKU, Product Name, Active status
   - SKU and Product Name are normalized to uppercase and trimmed
   - Uses upsert operation (creates if new, updates if exists)

2. **View Materials**

   - Displays all materials sorted by active status (active first) then SKU
   - Shows: SKU, Product Name, Active status, Created/Updated timestamps

3. **Edit Material Status** (Admin only)
   - Inline editing of Active status via data editor
   - Deactivated SKUs are hidden from dropdowns and filtered from inventory views
   - Save button commits changes to database

#### Locations Tab

1. **Create/Update Location**

   - Form to add new locations or update existing ones
   - Fields: Location name, Active status
   - Location names are normalized to uppercase and trimmed

2. **View Locations**

   - Displays all locations sorted by active status then name
   - Shows: Location, Active status, Created/Updated timestamps

3. **Edit Location Status** (Admin only)
   - Inline editing of Active status via data editor
   - Deactivated locations are hidden from dropdowns
   - Save button commits changes to database

**Collections used:**

- `MM` (read + upsert)
- `Locations` (read + upsert)

---

### Inbound Entry

**File:** `wms/pages/inbound.py`

**Purpose:** Add stock into inventory through multiple entry methods.

**Functions:**

#### Tab 1: Inbound Multi Entry (Scan Flow)

1. **Step 1: Scan SKU**

   - Auto-focused text input for barcode scanner
   - Validates SKU exists in Material Master and is active
   - Advances to Step 2 on Enter or Next button

2. **Step 2: Enter Details**

   - Shows scanned SKU
   - Input fields: Quantity, Location (dropdown of active locations)
   - Back button returns to Step 1

3. **Submit Process**
   - Validates SKU is active in Material Master
   - Upserts inventory record (increments quantity)
   - Creates inbound transaction
   - Creates movement document with transaction number (format: 1xxxxx, 6 digits)
   - Resets to Step 1 for next scan

#### Tab 2: Inbound Single Entry (Session-based Scanning)

1. **New Session**

   - Button to start a new scanning session
   - Clears previous session log

2. **Location Selection**

   - Dropdown to select destination location
   - Must be selected before scanning

3. **Scan Terminal**

   - Auto-focused input for continuous SKU scanning
   - Each scan adds 1 unit to session log
   - Validates SKU exists and is active
   - Displays success/error messages

4. **Session Log**

   - Live display of all scanned items
   - Shows: Timestamp, SKU, Product Name, Quantity
   - Inline delete functionality (remove scanned items before confirmation)
   - Shows total items scanned and total quantity

5. **Confirm Submit**
   - Aggregates quantities by SKU
   - Writes all items to inventory (upserts and increments)
   - Creates transaction records for each unique SKU
   - Creates single movement document for entire session
   - Resets session after successful submission

#### Tab 3: Manual Inbound Entry

1. **Manual Form**

   - Dropdowns: SKU (active only), Location (active only)
   - Number input: Quantity
   - Submit button

2. **Submit Process**
   - Same validation and database operations as scan flow
   - Creates inbound transaction and movement document

#### Current Inventory Status

- Displays all inventory items with quantity > 0
- Filters to show only active SKUs
- Read-only table view

**Collections used:**

- `MM` (read for validation and product name lookup)
- `Locations` (read for active location options)
- `inventory` (upsert + increment)
- `transactions` (insert)
- `movement` (insert)

---

### Outbound Processing

**Files:**

- UI: `wms/pages/outbound.py`
- Logic: `wms/outbound.py`

**Purpose:** Scanning terminal for outbound shipments with duplicate protection.

**Functions:**

1. **New Session**

   - Button to start new outbound session
   - Clears session log and resets state

2. **Station Location Selection**

   - Dropdown to select current station location
   - Only shows locations that exist in inventory
   - Custom sort order (numeric locations first, then alphabetic)

3. **Scan Terminal**

   - Auto-focused input field
   - Expects alternating scans: SKU → Shipment ID → SKU → Shipment ID...
   - Visual feedback shows which scan is expected next

4. **Scan Processing** (`process_scan()` in `wms/outbound.py`)
   - **First scan (SKU):** Validates SKU exists and is active, stores in scan pair
   - **Second scan (Shipment ID):** Completes the pair and processes outbound
5. **Duplicate Shipment Protection**

   - Checks if shipment_id already exists in transactions
   - If duplicate found:
     - Adds +1 back to previous inventory location
     - Deletes old transaction record
     - Removes old entry from session log
     - Processes new scan as replacement

6. **Inventory Decrement**

   - Decrements inventory by 1 at selected location
   - Only processes if quantity > 0
   - Shows error if insufficient stock

7. **Transaction Logging**

   - Creates `type="outbound"` transaction with shipment_id
   - Adds to session log (in-memory for quick export)

8. **Live Session Log**

   - Displays all scanned items in current session
   - Shows: Timestamp, SKU, Product Name, Shipment ID
   - Inline delete functionality (before confirmation)
   - Shows total items scanned

9. **Confirm Session Complete**

   - Button to finalize session (disabled until items scanned)
   - Creates movement document with transaction number (format: 2xxxxxxx, 8 digits)
   - Marks session as confirmed
   - Enables Excel export

10. **Export Session Data**

    - Downloads session log as Excel file
    - Only enabled after session confirmation

11. **Global Inventory Dashboard**
    - Shows current inventory levels (quantity > 0, active SKUs only)
    - Read-only view

**Collections used:**

- `inventory` (read + decrement, occasional rollback for duplicates)
- `transactions` (insert + delete for duplicates)
- `movement` (insert on session confirmation)
- `MM` (read for active status and product name)

---

### STO - Stock Transfer Order

**File:** `wms/pages/sto.py`

**Purpose:** Transfer stock between locations with full audit trail.

**Functions:**

1. **SKU Selection**

   - Dropdown of active SKUs from Material Master

2. **Location From/To**

   - Dropdown of active locations
   - "To" dropdown excludes selected "From" location
   - Shows available quantity at "From" location

3. **Quantity Input**

   - Number input with max value = available quantity
   - Prevents over-transfer

4. **Submit STO**

   - Validates SKU is active
   - Validates sufficient stock at From location
   - Validates From ≠ To

5. **Transfer Process**

   - **Outbound-style decrement:** Removes quantity from From location (atomic operation)
   - **Inbound-style increment:** Adds quantity to To location (upsert)
   - Creates two transactions:
     - `type="outbound"` with `sto=True` flag at From location
     - `type="inbound"` with `sto=True` flag at To location
   - Creates STO movement document with:
     - Transaction number (format: 1xxxx, 5 digits starting at 10000)
     - `delivery_locations` field: `{"from": "LOC1", "to": "LOC2"}`
     - Embedded details with both transactions

6. **Current Inventory**
   - Displays all inventory (quantity > 0, active SKUs only)
   - Read-only view

**Collections used:**

- `MM` (read for validation)
- `Locations` (read for active location options)
- `inventory` (atomic decrement + upsert increment)
- `transactions` (insert 2 records: outbound + inbound)
- `movement` (insert STO movement document)

---

### Transactions

**File:** `wms/pages/transactions.py`

**Purpose:** View, filter, and audit all inventory movements.

**Functions:**

1. **Load Transactions**

   - Fetches all transactions sorted newest-first
   - Filters to show only transactions for active SKUs
   - Converts UTC timestamps to US Central Time

2. **Quantity Normalization** (`_compute_qty()`)

   - Converts type-specific quantities to signed `qty` column:
     - `inbound` → `+inbound_qty`
     - `outbound` → `-outbound_qty`
     - `void` → `-void_qty`

3. **Product Name Backfill**

   - Fills missing product names from inventory collection
   - Uses (SKU, Location) mapping

4. **Filters** (`_apply_filters()`)

   - **SKU:** Multi-select dropdown (checkable items)
   - **Product Name:** Text search (contains)
   - **Shipment ID:** Text search (contains)
   - **Locations:** Multi-select dropdown of active locations
   - **Type:** Multi-select (inbound, outbound, void)
   - **Date Range:** Start and End date (inclusive, defaults to all dates → today)
   - **Duplicate Shipment IDs:** Checkbox to show only duplicated shipment IDs

5. **Display**
   - Shows filtered transaction count vs total
   - Total quantity metric for filtered transactions
   - Columns: Timestamp, SKU, Product Name, Shipment ID, Location, Type, Reason, STO flag, Location From/To, Qty

**Collections used:**

- `transactions` (read all)
- `inventory` (read for product name mapping)
- `MM` (read for active SKU filtering)
- `Locations` (read for active location filter options)

---

### Movements

**File:** `wms/pages/movements.py`

**Purpose:** View session-level movement documents with embedded transaction details.

**Functions:**

1. **Load Movements**

   - Fetches all movement documents sorted newest-first
   - Converts UTC timestamps to US Central Time

2. **Filters**

   - **Date Range:** Start and End date
   - **Movement Type:** Multi-select (inbound, outbound, void, sto)

3. **Display Table**

   - Columns: Timestamp, Movement Type, Transaction Num, Qty, Location, Delivery Locations (for STO), Details
   - Details column shows count of embedded records (e.g., "5 row(s)")
   - Delivery Locations shows destination for STO movements

4. **Transaction Number Search**

   - Text input to search by transaction number
   - Filters table to show only matching transaction
   - Examples: 100001 (inbound), 20000001 (outbound), 3001 (void), 10000 (STO)

5. **Details View**
   - Type transaction number to view full details
   - **For STO:** Shows compact movement document (no deconstruction)
   - **For other types:** Normalizes embedded details into table format
   - Timestamps converted to US Central Time

**Transaction Number Formats:**

- **Inbound:** 6 digits starting with '1' (e.g., 100001, 100002...)
- **Outbound:** 8 digits starting with '2' (e.g., 20000001, 20000002...)
- **Void:** 4 digits starting with '3' (e.g., 3001, 3002...)
- **STO:** 5 digits starting at 10000 (e.g., 10000, 10001...)

**Collections used:**

- `movement` (read all)

---

## Database Schema & Structure

This app uses **MongoDB** with database name: `warehouse_db`.

### Collections Overview

The system uses 6 main collections:

1. **`MM`** - Material Master (SKU definitions)
2. **`Locations`** - Location master data
3. **`inventory`** - Current stock positions
4. **`transactions`** - Immutable audit log of all movements
5. **`movement`** - Session-level movement documents
6. **`users`** - Authentication and user roles

### Collection Details

#### 1. `MM` (Material Master)

**Purpose:** Canonical SKU registry with active/inactive status.

**Document Structure:**

```json
{
  "sku": "ABC123",
  "product_name": "WIDGET",
  "active": true,
  "created_at": "2026-01-10T10:00:00Z",
  "updated_at": "2026-01-10T10:00:00Z"
}
```

**Key Fields:**

- `sku` (string, uppercase) – **Business key**, unique identifier
- `product_name` (string, uppercase) – Product description
- `active` (boolean) – Controls visibility in dropdowns and inventory views
- `created_at` (datetime) – Record creation timestamp
- `updated_at` (datetime) – Last modification timestamp

**Recommended Indexes:**

- Unique index on `sku`
- Index on `active` for filtering

**Business Rules:**

- SKU must exist in MM before inbound operations
- Deactivated SKUs are hidden from all dropdowns
- Deactivated SKUs are filtered from inventory and transaction views
- SKU and product_name are normalized to uppercase and trimmed

---

#### 2. `Locations`

**Purpose:** Location master data with active/inactive status.

**Document Structure:**

```json
{
  "location": "A01",
  "active": true,
  "created_at": "2026-01-10T10:00:00Z",
  "updated_at": "2026-01-10T10:00:00Z"
}
```

**Key Fields:**

- `location` (string, uppercase) – **Business key**, unique identifier
- `active` (boolean) – Controls visibility in dropdowns
- `created_at` (datetime) – Record creation timestamp
- `updated_at` (datetime) – Last modification timestamp

**Recommended Indexes:**

- Unique index on `location`
- Index on `active` for filtering

**Business Rules:**

- Location names are normalized to uppercase and trimmed
- Deactivated locations are hidden from all dropdowns
- Custom sort order: numeric locations first, then alphabetic

---

#### 3. `inventory`

**Purpose:** Current stock position by SKU and location.

**Document Structure:**

```json
{
  "sku": "ABC123",
  "product_name": "WIDGET",
  "location": "A01",
  "quantity": 100
}
```

**Key Fields:**

- `sku` (string, uppercase)
- `product_name` (string, uppercase)
- `location` (string, uppercase)
- `quantity` (integer) – Current stock level

**Business Key:**

- `(sku, location)` – Unique combination

**Recommended Indexes:**

- Unique compound index on `(sku, location)`
- Index on `location` for location-based queries
- Index on `sku` for SKU-based queries

**Business Rules:**

- Upserted on inbound operations (creates if new, increments if exists)
- Decremented on outbound operations (atomic decrement with quantity check)
- Quantity can be reduced to 0 but record remains (for audit trail)
- Admin void operations set quantity to 0
- Only active SKUs are displayed in UI views

---

#### 4. `transactions`

**Purpose:** Immutable audit log of all inventory movements.

**Document Structure (varies by type):**

**Inbound:**

```json
{
  "timestamp": "2026-01-10T10:00:00Z",
  "sku": "ABC123",
  "product_name": "WIDGET",
  "location": "A01",
  "type": "inbound",
  "inbound_qty": 50
}
```

**Outbound:**

```json
{
  "timestamp": "2026-01-10T10:00:00Z",
  "sku": "ABC123",
  "product_name": "WIDGET",
  "shipment_id": "SHIP001",
  "location": "A01",
  "type": "outbound",
  "outbound_qty": 1
}
```

**Void:**

```json
{
  "timestamp": "2026-01-10T10:00:00Z",
  "sku": "ABC123",
  "product_name": "WIDGET",
  "location": "A01",
  "type": "void",
  "void_qty": 10,
  "reason": "Inventory Editor quantity reduction"
}
```

**STO (creates 2 transactions):**

```json
{
  "timestamp": "2026-01-10T10:00:00Z",
  "sku": "ABC123",
  "product_name": "WIDGET",
  "shipment_id": "",
  "location": "A01",
  "type": "outbound",
  "outbound_qty": 25,
  "reason": "STO transfer out",
  "sto": true,
  "location_from": "A01",
  "location_to": "B02"
}
```

**Key Fields:**

- `timestamp` (datetime) – When transaction occurred
- `sku` (string, uppercase)
- `product_name` (string, uppercase)
- `location` (string, uppercase)
- `type` (string) – One of: "inbound", "outbound", "void"
- `shipment_id` (string) – For outbound only
- `inbound_qty` (integer) – For inbound type
- `outbound_qty` (integer) – For outbound type
- `void_qty` (integer) – For void type
- `reason` (string) – Optional explanation
- `sto` (boolean) – Flag for STO-related transactions
- `location_from` / `location_to` (string) – For STO only

**Recommended Indexes:**

- Index on `timestamp` (descending) for sorted queries
- Index on `shipment_id` for duplicate detection
- Index on `sku` for SKU-based filtering
- Index on `location` for location-based filtering
- Index on `type` for type-based filtering

**Business Rules:**

- Append-only (never updated or deleted, except duplicate shipment replacement)
- Every inventory change creates a transaction record
- Duplicate shipment_id triggers replacement logic (old transaction deleted)
- Timestamps stored in UTC, converted to US Central for display

---

#### 5. `movement`

**Purpose:** Session-level movement documents with embedded transaction details.

**Document Structure:**

**Inbound:**

```json
{
  "timestamp": "2026-01-10T10:00:00Z",
  "movement_type": "inbound",
  "transaction_num": "100001",
  "qty": 50,
  "location": "A01",
  "details": [
    {
      "timestamp": "2026-01-10T10:00:00Z",
      "sku": "ABC123",
      "product_name": "WIDGET",
      "location": "A01",
      "type": "inbound",
      "inbound_qty": 50
    }
  ]
}
```

**Outbound:**

```json
{
  "timestamp": "2026-01-10T10:00:00Z",
  "movement_type": "outbound",
  "transaction_num": "20000001",
  "qty": 25,
  "location": "A01",
  "details": [
    {
      "timestamp": "2026-01-10T10:00:00Z",
      "sku": "ABC123",
      "product_name": "WIDGET",
      "shipment_id": "SHIP001",
      "location": "A01",
      "type": "outbound",
      "outbound_qty": 1,
      "qty": -1
    }
    // ... more items
  ]
}
```

**STO:**

```json
{
  "timestamp": "2026-01-10T10:00:00Z",
  "movement_type": "sto",
  "transaction_num": "10000",
  "qty": 25,
  "location": "A01",
  "delivery_locations": {
    "from": "A01",
    "to": "B02"
  },
  "details": [
    {
      "timestamp": "2026-01-10T10:00:00Z",
      "sku": "ABC123",
      "product_name": "WIDGET",
      "qty": 25,
      "location_from": "A01",
      "location_to": "B02",
      "type": "sto",
      "shipment_id": ""
    },
    {"outbound": {...}},
    {"inbound": {...}}
  ]
}
```

**Key Fields:**

- `timestamp` (datetime) – Session completion time
- `movement_type` (string) – One of: "inbound", "outbound", "void", "sto"
- `transaction_num` (string) – Unique transaction number (format varies by type)
- `qty` (integer) – Total quantity in this movement
- `location` (string, uppercase) – Primary location
- `delivery_locations` (object) – For STO only: `{from, to}`
- `details` (array) – Embedded transaction records

**Transaction Number Formats:**

- **Inbound:** 6 digits starting with '1' (100001, 100002...) - uses atomic counter
- **Outbound:** 8 digits starting with '2' (20000001, 20000002...)
- **Void:** 4 digits starting with '3' (3001, 3002...)
- **STO:** 5 digits starting at 10000 (10000, 10001...)

**Recommended Indexes:**

- Index on `timestamp` (descending)
- Index on `transaction_num` for search
- Index on `movement_type` for filtering

**Business Rules:**

- Created when session is confirmed (outbound) or immediately (inbound/void/STO)
- Transaction numbers are auto-generated and sequential by type
- Inbound uses atomic counter in `counters` collection to prevent duplicates
- Details array contains embedded transaction records for audit trail
- Timestamps stored in UTC, converted to US Central for display

---

#### 6. `users`

**Purpose:** Authentication and authorization.

**Document Structure:**

```json
{
  "username": "admin",
  "password": "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
  "role": "admin"
}
```

**Key Fields:**

- `username` (string) – Unique username
- `password` (string) – SHA-256 hash of password
- `role` (string) – User role (e.g., "admin", "user")

**Recommended Indexes:**

- Unique index on `username`

**Business Rules:**

- Passwords are hashed with SHA-256 (see `wms/auth.py`)
- Admin role has edit permissions on inventory and master data
- Non-admin users have view-only access to inventory dashboard
- User provisioning is manual (no UI for user creation)

---

### Relationships

**Logical Relationships:**

1. **`MM.sku` → `inventory.sku`** (one-to-many)

   - One material can have multiple inventory records (different locations)
   - Inventory records must reference valid, active SKUs

2. **`Locations.location` → `inventory.location`** (one-to-many)

   - One location can contain multiple SKUs
   - Inventory records must reference valid, active locations

3. **`MM.sku` → `transactions.sku`** (one-to-many)

   - One material can have many transactions
   - Transactions reference SKUs for audit trail

4. **`inventory.(sku, location)` → `transactions.(sku, location)`** (logical)

   - Transactions record changes to specific inventory positions
   - Used for product name backfill in transaction views

5. **`transactions` → `movement.details`** (embedded)
   - Movement documents embed transaction records in details array
   - Provides session-level grouping of related transactions

**Referential Integrity:**

- Enforced at application level (not database constraints)
- SKU validation checks MM collection before inbound/outbound
- Active status filtering prevents operations on deactivated records
- Location validation checks Locations collection before operations

---

## Authentication / Roles

**Files:**

- `wms/auth.py` – Login form + SHA-256 hashing
- `wms/session.py` – Session state initialization

**Behavior:**

1. **Login Required**

   - If `st.session_state.authenticated` is false, shows login form and stops
   - Validates username/password against `users` collection
   - Passwords are SHA-256 hashed

2. **Roles:**

   - **`admin`**: Full access
     - Can edit inventory (with safeguards and audit logging)
     - Can edit master data (activate/deactivate SKUs and locations)
     - Can perform all operations
   - **`user`**: Limited access
     - View-only inventory dashboard
     - Can perform inbound/outbound/STO operations
     - Cannot edit master data or inventory directly

3. **Session State**

   - `st.session_state.authenticated` (boolean)
   - `st.session_state.username` (string)
   - `st.session_state.user_role` (string)

4. **User Provisioning**
   - No UI for user creation
   - Users must be added directly to `users` collection
   - Password must be SHA-256 hashed

---

## Configuration

**File:** `wms/config.py`

**Priority order:**

1. Environment variables (ex: `MONGO_URI`)
2. Streamlit secrets (ex: `mongo_uri`)

**Local Development:**

- Create `.env` file with `MONGO_URI=mongodb+srv://...`
- `python-dotenv` loads environment variables automatically

**Streamlit Cloud:**

- Add `mongo_uri` to Streamlit secrets
- Access via `st.secrets["mongo_uri"]`

**Required Configuration:**

- `MONGO_URI` or `mongo_uri` – MongoDB connection string

---

## Additional Features

### Timezone Handling

- All timestamps stored in UTC in database
- Converted to US Central Time for display
- Handled by `wms/timezone_utils.py`

### Excel Exports

- Outbound session data can be exported to Excel
- Uses `wms/ui_utils.py` `to_excel()` function
- Includes all transaction details with proper formatting

### Barcode Scanner Support

- Auto-focus on scan input fields
- JavaScript helpers in `wms/ui_utils.py`
- Disables F7 and F12 hotkeys from scanner devices
- Enter key triggers scan processing

### Custom Location Sorting

- Numeric locations sorted first (A01, A02...)
- Alphabetic locations sorted second
- Implemented in `wms/ui_utils.py` `sort_locations_custom()`

### Duplicate Shipment Protection

- Outbound scanning detects duplicate shipment IDs
- Automatically reverses previous transaction
- Processes new scan as replacement
- Maintains audit trail integrity

### Movement Transaction Numbering

- Auto-generated sequential numbers by type
- Inbound uses atomic counter (prevents duplicates in concurrent sessions)
- Other types use max+1 approach
- Implemented in `wms/movement.py`

---

## Summary

This WMS provides a complete inventory management solution with:

- **7 UI pages** for different operations
- **6 MongoDB collections** with clear relationships
- **Role-based access control** (admin vs user)
- **Complete audit trail** (transactions + movements)
- **Barcode scanner support** for efficient operations
- **Active/inactive status** for master data management
- **Duplicate protection** for outbound shipments
- **Session-based workflows** for batch operations
- **Excel exports** for reporting
- **Timezone handling** for accurate timestamps

All operations maintain data integrity through validation, atomic operations, and comprehensive audit logging.
