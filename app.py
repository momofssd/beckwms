import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import io

# --- 1. UI CONFIGURATION ---
st.set_page_config(page_title="WMS", layout="wide")

# --- 2. DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        uri = st.secrets["mongo_uri"]
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping') # Verify connection
        return client
    except Exception as e:
        st.error(f"⚠️ Connection failed: {e}")
        return None

client = init_connection()
if client:
    db = client["warehouse_db"]
    inventory_col = db["inventory"]
    transactions_col = db["transactions"]
    st.sidebar.info("System Status: Connected to Local Device")
else:
    st.stop()

# --- 3. HELPER FUNCTIONS ---
def auto_focus_js():
    """Maintains focus on the scanner terminal for high-speed operation."""
    components.html("<script>function setFocus(){const input=window.parent.document.querySelector('input[aria-label=\"SCAN_ZONE\"]');if(input&&window.parent.document.activeElement!==input){input.focus();}}setInterval(setFocus,300);setTimeout(setFocus,100);</script>", height=0)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def process_scan():
    """Processes barcode input for outbound transactions."""
    scan_val = st.session_state.main_scanner
    if scan_val:
        st.session_state.scan_pair.append(scan_val.strip().upper())
        if len(st.session_state.scan_pair) == 2:
            sku, tracking = st.session_state.scan_pair[0], st.session_state.scan_pair[1]
            loc = st.session_state.current_loc
            ts = datetime.now()
            
            # Replacement logic for duplicate shipment IDs
            existing = transactions_col.find_one({"shipment_id": tracking})
            if existing:
                inventory_col.update_one({"sku": existing["sku"], "location": existing["location"]}, {"$inc": {"quantity": 1}})
                transactions_col.delete_one({"_id": existing["_id"]})
                st.session_state.session_log = [l for l in st.session_state.session_log if l['shipment_id'] != tracking]
                st.toast(f"Tracking {tracking} replaced.")

            res = inventory_col.update_one({"sku": sku, "location": loc, "quantity": {"$gt": 0}}, {"$inc": {"quantity": -1}})
            if res.modified_count > 0:
                entry = {"timestamp": ts, "sku": sku, "shipment_id": tracking, "location": loc, "type": "outbound", "outbound_qty": 1}
                transactions_col.insert_one(entry.copy())
                st.session_state.session_log.insert(0, entry)
                st.session_state.last_msg = ("success", f"Processed: {sku}")
            else:
                st.session_state.last_msg = ("error", f"Error: {sku} out of stock.")
            st.session_state.scan_pair = []
        st.session_state.main_scanner = ""

# --- 4. SESSION STATE INITIALIZATION ---
for key in ["scan_pair", "session_log", "page", "last_msg"]:
    if key not in st.session_state: 
        st.session_state[key] = [] if "log" in key or "pair" in key else "outbound" if "page" in key else (None, None)

# --- 5. NAVIGATION ---
st.sidebar.title("WMS Navigation")
if st.sidebar.button("Inventory Dashboard", use_container_width=True): st.session_state.page = "home"
if st.sidebar.button("Outbound Processing", use_container_width=True): st.session_state.page = "outbound"
if st.sidebar.button("Inbound Entry", use_container_width=True): st.session_state.page = "inbound"

# --- 6. PAGE CONTENT ---
file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

if st.session_state.page == "home":
    st.title("Inventory Management")
    raw_data = list(inventory_col.find())
    
    if raw_data:
        df_display = pd.DataFrame(raw_data)
        st.subheader("Inventory Editor")
        
        # Capture precise user edits using the state dictionary
        edited_data = st.data_editor(
            df_display, 
            column_config={"_id": None}, 
            num_rows="dynamic", 
            use_container_width=True,
            key="inventory_table"
        )
        
        if st.button("Apply Changes and Sync Database", type="primary"):
            state = st.session_state.inventory_table
            
            # 1. Handle Precise Deletions
            deleted_rows = state.get("deleted_rows", [])
            for row_idx in deleted_rows:
                doc_id = df_display.iloc[row_idx]["_id"]
                inventory_col.delete_one({"_id": doc_id})

            # 2. Handle Precise Updates (only modified rows)
            edited_rows = state.get("edited_rows", {})
            for row_idx_str, changes in edited_rows.items():
                row_idx = int(row_idx_str)
                doc_id = df_display.iloc[row_idx]["_id"]
                
                # Fetch existing row values to merge with changes
                current_row = df_display.iloc[row_idx].to_dict()
                updated_values = {
                    "sku": str(changes.get("sku", current_row["sku"])).strip().upper(),
                    "name": str(changes.get("name", current_row["name"])).strip().upper(),
                    "location": str(changes.get("location", current_row["location"])).strip().upper(),
                    "quantity": int(changes.get("quantity", current_row["quantity"]))
                }
                inventory_col.update_one({"_id": doc_id}, {"$set": updated_values})

            # 3. Handle Added Rows
            added_rows = state.get("added_rows", [])
            for row in added_rows:
                if "sku" in row and "location" in row:
                    new_doc = {
                        "sku": str(row.get("sku", "")).strip().upper(),
                        "name": str(row.get("name", "")).strip().upper(),
                        "location": str(row.get("location", "")).strip().upper(),
                        "quantity": int(row.get("quantity", 0))
                    }
                    inventory_col.insert_one(new_doc)

            st.success("Database synchronized successfully.")
            st.rerun()
    else:
        st.info("Inventory database is currently empty.")

elif st.session_state.page == "outbound":
    st.title("Outbound Terminal")
    all_locs = sorted(inventory_col.distinct("location"))
    st.session_state.current_loc = st.selectbox("Select Station", options=all_locs, index=None)
    if st.session_state.current_loc:
        st.divider()
        msg_t, msg_x = st.session_state.last_msg
        if msg_t == "success": st.success(msg_x)
        if msg_t == "error": st.error(msg_x)
        st.text_input("SCAN_ZONE", key="main_scanner", on_change=process_scan, label_visibility="collapsed")
        auto_focus_js()
    if st.session_state.session_log:
        df_s = pd.DataFrame(st.session_state.session_log)
        order = ["shipment_id", "sku", "location", "type", "timestamp", "outbound_qty"]
        st.download_button("Export Session Data", data=to_excel(df_s[order]), file_name=f"session_{file_ts}.xlsx")
        st.table(df_s[['sku', 'shipment_id']])

elif st.session_state.page == "inbound":
    st.title("Inbound Entry")
    with st.form("inbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        sku = c1.text_input("SKU").upper()
        name = c2.text_input("Product Name").upper()
        qty = c1.number_input("Quantity", min_value=1)
        loc = c2.text_input("Location").upper()
        if st.form_submit_button("Submit Stock Entry", use_container_width=True):
            inventory_col.update_one({"sku": sku, "location": loc}, {"$set": {"name": name}, "$inc": {"quantity": int(qty)}}, upsert=True)
            transactions_col.insert_one({"timestamp": datetime.now(), "sku": sku, "location": loc, "type": "inbound", "inbound_qty": int(qty)})
            st.success(f"Entry Successful: {qty} units of {sku}")