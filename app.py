import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import io

# --- 1. DATABASE CONNECTION (Atlas Cloud Ready) ---
@st.cache_resource
# Simplified Connection Logic
def init_connection():
    try:
        # Looking for a single top-level key
        uri = st.secrets["mongo_uri"] 
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client
    except Exception as e:
        st.error(f"⚠️ Connection failed: {e}")
        return None

client = init_connection()
if client:
    db = client["warehouse_db"]
    inventory_col = db["inventory"]
    transactions_col = db["transactions"]
else:
    st.stop()

# --- 2. AUTO-FOCUS JAVASCRIPT ---
def auto_focus_js():
    """Forces cursor back to scan zone for hands-free operation."""
    components.html(
        """
        <script>
            function setFocus() {
                const input = window.parent.document.querySelector('input[aria-label="SCAN_ZONE"]');
                if (input && window.parent.document.activeElement !== input) {
                    input.focus();
                }
            }
            setInterval(setFocus, 300); 
            setTimeout(setFocus, 100);
        </script>
        """,
        height=0,
    )

# --- 3. HELPER FUNCTIONS ---
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def process_scan():
    """Handles logic for Outbound scans with session isolation and uppercase conversion."""
    scan_val = st.session_state.main_scanner
    
    if scan_val:
        # Convert all scans to UPPERCASE immediately
        st.session_state.scan_pair.append(scan_val.strip().upper())
        
        if len(st.session_state.scan_pair) == 2:
            sku_found = st.session_state.scan_pair[0]
            tracking_found = st.session_state.scan_pair[1]
            selected_loc = st.session_state.current_loc
            ts = datetime.now()
            
            # DUPLICATE HANDLING (Shared DB Check)
            existing_tx = transactions_col.find_one({"shipment_id": tracking_found})
            if existing_tx:
                inventory_col.update_one(
                    {"sku": existing_tx["sku"], "location": existing_tx["location"]},
                    {"$inc": {"quantity": 1}}
                )
                transactions_col.delete_one({"_id": existing_tx["_id"]})
                # Update current user's session log display
                st.session_state.session_log = [log for log in st.session_state.session_log if log['shipment_id'] != tracking_found]
                st.toast(f"🔄 Duplicate tracking replaced.", icon="⚠️")

            # PROCESS TRANSACTION
            update_res = inventory_col.update_one(
                {"sku": sku_found, "location": selected_loc, "quantity": {"$gt": 0}},
                {"$inc": {"quantity": -1}}
            )

            if update_res.modified_count > 0:
                new_entry = {
                    "timestamp": ts,
                    "sku": sku_found,
                    "shipment_id": tracking_found,
                    "location": selected_loc,
                    "type": "outbound",
                    "outbound_qty": 1
                }
                transactions_col.insert_one(new_entry.copy())
                st.session_state.session_log.insert(0, new_entry)
                st.session_state.last_msg = ("success", f"✅ Shipped: {sku_found}")
            else:
                st.session_state.last_msg = ("error", f"❌ Error: {sku_found} out of stock.")
            
            st.session_state.scan_pair = []
        
        st.session_state.main_scanner = ""

# --- 4. SESSION STATE INIT ---
st.set_page_config(page_title="Inventory WMS", layout="wide")

if "scan_pair" not in st.session_state: st.session_state.scan_pair = [] 
if "session_log" not in st.session_state: st.session_state.session_log = [] 
if "page" not in st.session_state: st.session_state.page = "outbound"
if "last_msg" not in st.session_state: st.session_state.last_msg = (None, None)

# --- 5. SIDEBAR NAVIGATION ---
st.sidebar.title("WMS Control Panel")
if st.sidebar.button("🏠 Home", use_container_width=True): st.session_state.page = "home"
if st.sidebar.button("📤 Outbound (Scan Out)", use_container_width=True): st.session_state.page = "outbound"
if st.sidebar.button("📥 Inbound", use_container_width=True): st.session_state.page = "inbound"

# --- 6. PAGE CONTENT ---
file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# HOME
if st.session_state.page == "home":
    st.title("📦 Warehouse Dashboard")
    total_items = inventory_col.count_documents({})
    st.metric("Unique SKUs in System", total_items)

# OUTBOUND
elif st.session_state.page == "outbound":
    head_l, head_r = st.columns([3, 1])
    head_l.title("📤 Outbound Processing")
    if head_r.button("✨ New Session", use_container_width=True):
        st.session_state.session_log, st.session_state.scan_pair = [], []
        st.session_state.last_msg = (None, None)
        st.rerun()
    
    col_left, col_right = st.columns([1, 1], gap="large")
    with col_left:
        st.subheader("Scan Terminal")
        all_locs = sorted(inventory_col.distinct("location"))
        st.session_state.current_loc = st.selectbox("Location", options=all_locs, index=None)

        if st.session_state.current_loc:
            st.divider()
            msg_type, msg_text = st.session_state.last_msg
            if msg_type == "success": st.success(msg_text)
            if msg_type == "error": st.error(msg_text)
            st.text_input("SCAN_ZONE", key="main_scanner", on_change=process_scan, label_visibility="collapsed")
            auto_focus_js()

    with col_right:
        log_h, log_b = st.columns([2, 1])
        log_h.subheader("Live Session Log")
        if st.session_state.session_log:
            df_sess = pd.DataFrame(st.session_state.session_log)
            # EXPORT ORDER: shipment_id, sku, location, type, timestamp, outbound_qty
            column_order = ["shipment_id", "sku", "location", "type", "timestamp", "outbound_qty"]
            df_export = df_sess[[c for c in column_order if c in df_sess.columns]].copy()
            df_export['timestamp'] = df_export['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            log_b.download_button("📥 Export Session", data=to_excel(df_export), file_name=f"session_{file_ts}.xlsx")
            st.table(df_sess[['sku', 'shipment_id']])

# INBOUND
elif st.session_state.page == "inbound":
    st.title("📥 Inbound Stock Entry")
    with st.form("inbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        sku_r = c1.text_input("SKU Barcode*")
        name_r = c2.text_input("Product Name*")
        qty = c1.number_input("Quantity*", min_value=1, step=1)
        loc_r = c2.text_input("Location*")
        if st.form_submit_button("Confirm Inbound Entry", use_container_width=True):
            if sku_r and name_r and loc_r:
                sku_u, name_u, loc_u = sku_r.strip().upper(), name_r.strip().upper(), loc_r.strip().upper()
                inventory_col.update_one({"sku": sku_u, "location": loc_u}, {"$set": {"name": name_u}, "$inc": {"quantity": int(qty)}}, upsert=True)
                transactions_col.insert_one({"timestamp": datetime.now(), "sku": sku_u, "location": loc_u, "type": "inbound", "inbound_qty": int(qty)})
                st.success(f"✅ Added {qty} units of {sku_u}")
            else: st.error("⚠️ All fields required.")

# --- 7. INVENTORY VIEW (SHARED) ---
st.divider()
inv_h, btn_tx, btn_stk = st.columns([3, 1, 1])
inv_h.subheader("📊 Current Warehouse Stock")

# Global Transaction Export
all_tx = list(transactions_col.find({"type": "outbound"}, {"_id": 0}))
if all_tx:
    df_all = pd.DataFrame(all_tx)
    # Match Header Order
    order = ["shipment_id", "sku", "location", "type", "timestamp", "outbound_qty"]
    df_all = df_all[[c for c in order if c in df_all.columns]]
    df_all['timestamp'] = df_all['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    btn_tx.download_button("📥 Export Transaction", data=to_excel(df_all), file_name=f"all_tx_{file_ts}.xlsx")

inventory_data = list(inventory_col.find({}, {"_id": 0}))
if inventory_data:
    df_inv = pd.DataFrame(inventory_data)
    btn_stk.download_button("📥 Export Stock", data=to_excel(df_inv), file_name=f"inv_{file_ts}.xlsx")
    st.dataframe(df_inv, use_container_width=True)