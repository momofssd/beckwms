import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import io

# --- 1. UI CONFIGURATION ---
st.set_page_config(page_title="Beck's WMS - Local", layout="wide")

# --- 2.  DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        uri = st.secrets["mongo_uri"]
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.server_info() 
        return client
    except Exception as e:
        st.error("Connection Error: Local MongoDB not detected. Please ensure MongoDB service is running.")
        st.stop()
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
    components.html("<script>function setFocus(){const input=window.parent.document.querySelector('input[aria-label=\"SCAN_ZONE\"]');if(input&&window.parent.document.activeElement!==input){input.focus();}}setInterval(setFocus,300);setTimeout(setFocus,100);</script>", height=0)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def process_scan():
    scan_val = st.session_state.main_scanner
    if scan_val:
        st.session_state.scan_pair.append(scan_val.strip().upper())
        if len(st.session_state.scan_pair) == 2:
            sku_found = st.session_state.scan_pair[0]
            tracking_found = st.session_state.scan_pair[1]
            selected_loc = st.session_state.current_loc
            ts = datetime.now()
            
            existing_tx = transactions_col.find_one({"shipment_id": tracking_found})
            if existing_tx:
                inventory_col.update_one({"sku": existing_tx["sku"], "location": existing_tx["location"]}, {"$inc": {"quantity": 1}})
                transactions_col.delete_one({"_id": existing_tx["_id"]})
                st.session_state.session_log = [log for log in st.session_state.session_log if log['shipment_id'] != tracking_found]
                st.toast(f"Tracking {tracking_found} replaced.")

            update_res = inventory_col.update_one({"sku": sku_found, "location": selected_loc, "quantity": {"$gt": 0}}, {"$inc": {"quantity": -1}})
            if update_res.modified_count > 0:
                new_entry = {"timestamp": ts, "sku": sku_found, "shipment_id": tracking_found, "location": selected_loc, "type": "outbound", "outbound_qty": 1}
                transactions_col.insert_one(new_entry.copy())
                st.session_state.session_log.insert(0, new_entry)
                st.session_state.last_msg = ("success", f"Processed: {sku_found}")
            else:
                st.session_state.last_msg = ("error", f"Error: {sku_found} out of stock at {selected_loc}")
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
        edited_data = st.data_editor(df_display, column_config={"_id": None}, num_rows="dynamic", use_container_width=True, key="inventory_table")
        
        # Standard width button (no use_container_width)
        if st.button("Apply Changes and Sync Database", type="primary"):
            state = st.session_state.inventory_table
            for row_idx in state.get("deleted_rows", []): inventory_col.delete_one({"_id": df_display.iloc[row_idx]["_id"]})
            for row_idx_str, changes in state.get("edited_rows", {}).items():
                row_idx = int(row_idx_str)
                doc_id = df_display.iloc[row_idx]["_id"]
                current_row = df_display.iloc[row_idx].to_dict()
                updated_values = {"sku": str(changes.get("sku", current_row["sku"])).strip().upper(), "name": str(changes.get("name", current_row["name"])).strip().upper(), "location": str(changes.get("location", current_row["location"])).strip().upper(), "quantity": int(changes.get("quantity", current_row["quantity"]))}
                inventory_col.update_one({"_id": doc_id}, {"$set": updated_values})
            for row in state.get("added_rows", []): inventory_col.insert_one({"sku": str(row.get("sku", "")).strip().upper(), "name": str(row.get("name", "")).strip().upper(), "location": str(row.get("location", "")).strip().upper(), "quantity": int(row.get("quantity", 0))})
            st.success("Database synchronized successfully.")
            st.rerun()
    else: st.info("Inventory database is currently empty.")

elif st.session_state.page == "outbound":
    head_l, head_r = st.columns([3, 1])
    head_l.title("Outbound Terminal")
    if head_r.button("New Session", use_container_width=True):
        st.session_state.session_log, st.session_state.scan_pair = [], []
        st.session_state.last_msg = (None, None)
        st.rerun()
    
    col_left, col_right = st.columns([1, 1], gap="large")
    with col_left:
        st.subheader("Scan Terminal")
        all_locs = sorted(inventory_col.distinct("location"))
        st.session_state.current_loc = st.selectbox("Select Station Location", options=all_locs, index=None)
        if st.session_state.current_loc:
            st.divider()
            msg_t, msg_x = st.session_state.last_msg
            if msg_t == "success": st.success(msg_x)
            if msg_t == "error": st.error(msg_x)
            st.text_input("SCAN_ZONE", key="main_scanner", on_change=process_scan, label_visibility="collapsed")
            auto_focus_js()
            if len(st.session_state.scan_pair) == 0: st.info("Awaiting SKU scan...")
            else: st.warning(f"SKU {st.session_state.scan_pair[0]} captured. Scan Shipment ID now.")

    with col_right:
        st.subheader("Live Session Log")
        if st.session_state.session_log:
            df_s = pd.DataFrame(st.session_state.session_log)
            order = ["shipment_id", "sku", "location", "type", "timestamp", "outbound_qty"]
            st.download_button("Export Session Data", data=to_excel(df_s[order]), file_name=f"session_{file_ts}.xlsx", use_container_width=True)
            st.table(df_s[['sku', 'shipment_id']])
        else: st.caption("No scans in this session.")

    st.divider()
    inv_h, btn_tx, btn_stk = st.columns([2, 1, 1])
    inv_h.subheader("Global Inventory Dashboard")
    
    all_tx = list(transactions_col.find({"type": "outbound"}, {"_id": 0}))
    if all_tx:
        df_all = pd.DataFrame(all_tx)
        order_all = ["shipment_id", "sku", "location", "type", "timestamp", "outbound_qty"]
        btn_tx.download_button("Export Global Transactions", data=to_excel(df_all[order_all]), file_name=f"all_tx_{file_ts}.xlsx", use_container_width=True)
    
    inventory_data = list(inventory_col.find({}, {"_id": 0}))
    if inventory_data:
        df_inv = pd.DataFrame(inventory_data)
        btn_stk.download_button("Export Current Stock", data=to_excel(df_inv), file_name=f"inventory_{file_ts}.xlsx", use_container_width=True)
        st.dataframe(df_inv, use_container_width=True)

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