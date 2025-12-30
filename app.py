import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import io

# --- 1. DATABASE CONNECTION ---
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
else:
    st.stop()

# --- 2. HELPERS & JS ---
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
            sku, tracking = st.session_state.scan_pair[0], st.session_state.scan_pair[1]
            loc = st.session_state.current_loc
            ts = datetime.now()
            
            # Duplicate/Replacement Logic
            existing = transactions_col.find_one({"shipment_id": tracking})
            if existing:
                inventory_col.update_one({"sku": existing["sku"], "location": existing["location"]}, {"$inc": {"quantity": 1}})
                transactions_col.delete_one({"_id": existing["_id"]})
                st.session_state.session_log = [l for l in st.session_state.session_log if l['shipment_id'] != tracking]
                st.toast(f"🔄 Tracking {tracking} replaced.", icon="⚠️")

            # Finalize Transaction
            res = inventory_col.update_one({"sku": sku, "location": loc, "quantity": {"$gt": 0}}, {"$inc": {"quantity": -1}})
            if res.modified_count > 0:
                entry = {"timestamp": ts, "sku": sku, "shipment_id": tracking, "location": loc, "type": "outbound", "outbound_qty": 1}
                transactions_col.insert_one(entry.copy())
                st.session_state.session_log.insert(0, entry)
                st.session_state.last_msg = ("success", f"✅ Shipped: {sku}")
            else:
                st.session_state.last_msg = ("error", f"❌ Error: {sku} out of stock.")
            st.session_state.scan_pair = []
        st.session_state.main_scanner = ""

# --- 3. UI CONFIG ---
st.set_page_config(page_title="Beck's Cloud WMS", layout="wide")
for key in ["scan_pair", "session_log", "page", "last_msg"]:
    if key not in st.session_state: 
        st.session_state[key] = [] if "log" in key or "pair" in key else "outbound" if "page" in key else (None, None)

# --- 4. NAVIGATION ---
st.sidebar.title("Beck's WMS")
if st.sidebar.button("🏠 Inventory Home"): st.session_state.page = "home"
if st.sidebar.button("📤 Outbound Scan"): st.session_state.page = "outbound"
if st.sidebar.button("📥 Inbound Entry"): st.session_state.page = "inbound"

# --- 5. PAGES ---
file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

if st.session_state.page == "home":
    st.title("📊 Inventory Dashboard & Editor")
    raw_data = list(inventory_col.find())
    if raw_data:
        df_edit = pd.DataFrame(raw_data)
        edited_df = st.data_editor(df_edit, column_config={"_id": None}, num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 Apply Changes & Delete", type="primary"):
            # Deletion Logic
            orig_ids = [i['_id'] for i in raw_data]
            rem_ids = edited_df['_id'].tolist() if not edited_df.empty else []
            for d_id in [oid for oid in orig_ids if oid not in rem_ids]:
                inventory_col.delete_one({"_id": d_id})
            # Update Logic
            for _, row in edited_df.iterrows():
                inventory_col.update_one({"_id": row["_id"]}, {"$set": {"sku": str(row["sku"]).upper(), "name": str(row["name"]).upper(), "location": str(row["location"]).upper(), "quantity": int(row["quantity"])}})
            st.success("Cloud Synchronized!")
            st.rerun()
    else: st.info("No stock found.")

elif st.session_state.page == "outbound":
    st.title("📤 Outbound Processing")
    all_locs = sorted(inventory_col.distinct("location"))
    st.session_state.current_loc = st.selectbox("Current Station", options=all_locs, index=None)
    if st.session_state.current_loc:
        msg_t, msg_x = st.session_state.last_msg
        if msg_t == "success": st.success(msg_x)
        if msg_t == "error": st.error(msg_x)
        st.text_input("SCAN_ZONE", key="main_scanner", on_change=process_scan, label_visibility="collapsed")
        auto_focus_js()
    if st.session_state.session_log:
        df_s = pd.DataFrame(st.session_state.session_log)
        # 3PL Export Order
        order = ["shipment_id", "sku", "location", "type", "timestamp", "outbound_qty"]
        st.download_button("📥 Export Session", data=to_excel(df_s[order]), file_name=f"session_{file_ts}.xlsx")
        st.table(df_s[['sku', 'shipment_id']])

elif st.session_state.page == "inbound":
    st.title("📥 Inbound Entry")
    with st.form("inbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        sku = c1.text_input("SKU*").upper()
        name = c2.text_input("Name*").upper()
        qty = c1.number_input("Qty*", min_value=1)
        loc = c2.text_input("Loc*").upper()
        if st.form_submit_button("Submit"):
            inventory_col.update_one({"sku": sku, "location": loc}, {"$set": {"name": name}, "$inc": {"quantity": int(qty)}}, upsert=True)
            transactions_col.insert_one({"timestamp": datetime.now(), "sku": sku, "location": loc, "type": "inbound", "inbound_qty": int(qty)})
            st.success(f"Added {qty} of {sku}")