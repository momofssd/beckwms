import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import io

# --- 1. DATABASE CONNECTION ---
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    db = client["warehouse_db"]
    inventory_col = db["inventory"]
    transactions_col = db["transactions"]
    client.server_info()
except Exception as e:
    st.error("⚠️ Local MongoDB not detected. Please start MongoDB Compass/Service.")
    st.stop()

# --- 2. AUTO-FOCUS JAVASCRIPT ---
def auto_focus_js():
    """Forces the browser to keep the cursor in the scan box at all times."""
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
    """Callback function to handle scans with uppercase conversion."""
    scan_val = st.session_state.main_scanner
    
    if scan_val:
        # Convert scan to uppercase immediately
        st.session_state.scan_pair.append(scan_val.strip().upper())
        
        if len(st.session_state.scan_pair) == 2:
            sku_found = st.session_state.scan_pair[0]
            tracking_found = st.session_state.scan_pair[1]
            selected_loc = st.session_state.current_loc # Already upper from selectbox
            ts = datetime.now()
            
            # --- DUPLICATE HANDLING ---
            existing_tx = transactions_col.find_one({"shipment_id": tracking_found})
            if existing_tx:
                inventory_col.update_one(
                    {"sku": existing_tx["sku"], "location": existing_tx["location"]},
                    {"$inc": {"quantity": 1}}
                )
                transactions_col.delete_one({"_id": existing_tx["_id"]})
                st.session_state.session_log = [log for log in st.session_state.session_log if log['shipment_id'] != tracking_found]
                st.toast(f"🔄 Duplicate tracking {tracking_found} replaced.", icon="⚠️")

            # --- PROCESS NEW TRANSACTION ---
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
                st.session_state.last_msg = ("error", f"❌ Error: {sku_found} out of stock at {selected_loc}")
            
            st.session_state.scan_pair = []
        
        st.session_state.main_scanner = ""

# --- 4. SESSION STATE INIT ---
st.set_page_config(page_title="Inbound Outbound WMS", layout="wide")

if "scan_pair" not in st.session_state:
    st.session_state.scan_pair = [] 
if "session_log" not in st.session_state:
    st.session_state.session_log = [] 
if "page" not in st.session_state:
    st.session_state.page = "outbound"
if "last_msg" not in st.session_state:
    st.session_state.last_msg = (None, None)
if "current_loc" not in st.session_state:
    st.session_state.current_loc = None

# --- 5. SIDEBAR NAVIGATION ---
st.sidebar.title("WMS Control Panel")
if st.sidebar.button("🏠 Home", use_container_width=True):
    st.session_state.page = "home"
if st.sidebar.button("📤 Outbound (Scan Out)", use_container_width=True):
    st.session_state.page = "outbound"
if st.sidebar.button("📥 Inbound", use_container_width=True):
    st.session_state.page = "inbound"

# --- 6. PAGE CONTENT ---
file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

if st.session_state.page == "home":
    st.title("📦 Warehouse Dashboard")
    total_items = inventory_col.count_documents({})
    c1, c2 = st.columns(2)
    c1.metric("Unique SKUs", total_items)

elif st.session_state.page == "outbound":
    head_l, head_r = st.columns([3, 1])
    head_l.title("📤 Outbound Processing")
    if head_r.button("✨ New Session", use_container_width=True):
        st.session_state.session_log = []
        st.session_state.scan_pair = []
        st.session_state.last_msg = (None, None)
        st.rerun()
    
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.subheader("Scan Terminal")
        # Locations from DB are already upper, but we ensure the dropdown handles them well
        all_locs = sorted(inventory_col.distinct("location"))
        st.session_state.current_loc = st.selectbox(
            "Step 1: Current Location", options=all_locs, index=None, placeholder="Select a location to start..."
        )

        if st.session_state.current_loc:
            st.divider()
            msg_type, msg_text = st.session_state.last_msg
            if msg_type == "success": st.success(msg_text)
            if msg_type == "error": st.error(msg_text)

            if not st.session_state.scan_pair:
                st.info("🎯 **ACTION:** Scan SKU Barcode")
            else:
                st.warning(f"📦 **SKU LOADED:** {st.session_state.scan_pair[0]} \n👉 **NEXT:** Scan Shipment Tracking")

            st.text_input("SCAN_ZONE", key="main_scanner", on_change=process_scan, label_visibility="collapsed")
            auto_focus_js()

    with col_right:
        log_head, log_btn = st.columns([2, 1])
        log_head.subheader("Live Transaction Log")
        
        if st.session_state.session_log:
            df_session = pd.DataFrame(st.session_state.session_log)
            column_order = ["timestamp", "sku", "shipment_id", "location", "type", "outbound_qty"]
            df_export = df_session[[c for c in column_order if c in df_session.columns]].copy()
            df_export['timestamp'] = df_export['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            log_btn.download_button("📥 Export Session", data=to_excel(df_export), file_name=f"session_shipments_{file_ts}.xlsx", use_container_width=True)

            df_display = df_session.copy()
            df_display['time'] = df_display['timestamp'].dt.strftime('%H:%M:%S')
            st.table(df_display[['time', 'sku', 'shipment_id']])
        else:
            st.info("No activity in this session yet.")

# --- INBOUND MODULE (Uppercase Enabled) ---
elif st.session_state.page == "inbound":
    st.title("📥 Inbound Stock Entry")
    st.write("Item details will be converted to UPPERCASE automatically.")
    
    with st.form("inbound_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            sku_raw = st.text_input("SKU Barcode*")
            name_raw = st.text_input("Product Name*")
        with col2:
            quantity = st.number_input("Quantity to Add*", min_value=1, step=1)
            location_raw = st.text_input("Warehouse Location*")
        
        submit_btn = st.form_submit_button("Confirm Inbound Entry", use_container_width=True)
        
        if submit_btn:
            if not sku_raw or not name_raw or not location_raw:
                st.error("⚠️ All fields are required to process inbound.")
            else:
                # Convert all strings to UPPERCASE before database entry
                sku_upper = sku_raw.strip().upper()
                name_upper = name_raw.strip().upper()
                loc_upper = location_raw.strip().upper()

                inventory_col.update_one(
                    {"sku": sku_upper, "location": loc_upper},
                    {"$set": {"name": name_upper}, "$inc": {"quantity": int(quantity)}},
                    upsert=True
                )
                
                transactions_col.insert_one({
                    "timestamp": datetime.now(),
                    "sku": sku_upper,
                    "location": loc_upper,
                    "type": "inbound",
                    "inbound_qty": int(quantity)
                })
                
                st.success(f"✅ Successfully added {quantity} units of {sku_upper} to {loc_upper}")

# --- 7. INVENTORY VIEW ---
st.divider()
inv_head_col, btn_tx_col, btn_stock_col = st.columns([3, 1, 1])
inv_head_col.subheader("📊 Current Warehouse Stock")

full_tx = list(transactions_col.find({"type": "outbound"}, {"_id": 0}))
if full_tx:
    df_full_tx = pd.DataFrame(full_tx)
    df_full_tx['outbound_qty'] = 1
    df_full_tx = df_full_tx[["timestamp", "sku", "shipment_id", "location", "type", "outbound_qty"]]
    df_full_tx['timestamp'] = df_full_tx['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    btn_tx_col.download_button("📥 Export Transaction", data=to_excel(df_full_tx), file_name=f"transactions_{file_ts}.xlsx", use_container_width=True)

inventory_data = list(inventory_col.find({}, {"_id": 0}))
if inventory_data:
    df_inv = pd.DataFrame(inventory_data)
    btn_stock_col.download_button("📥 Export Stock", data=to_excel(df_inv), file_name=f"inventory_{file_ts}.xlsx", use_container_width=True)
    st.dataframe(df_inv, use_container_width=True)