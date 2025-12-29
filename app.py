import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
from datetime import datetime
import pandas as pd
import io

# --- 1. DATABASE CONNECTION ---
try:
    # Adding maxPoolSize and waitQueueTimeout for better performance during rapid scans
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
            setInterval(setFocus, 300); // Check every 300ms for faster response
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
    """Callback function to handle scans without crashing the session state."""
    scan_val = st.session_state.main_scanner
    
    if scan_val:
        # Add the scan to our buffer
        st.session_state.scan_buffer.append(scan_val)
        
        # Check if we have both SKU and Tracking
        if len(st.session_state.scan_buffer) == 2:
            sku_found = st.session_state.scan_buffer[0]
            tracking_found = st.session_state.scan_buffer[1]
            selected_loc = st.session_state.current_loc
            
            # Database Update Logic
            update_res = inventory_col.update_one(
                {"sku": sku_found, "location": selected_loc, "quantity": {"$gt": 0}},
                {"$inc": {"quantity": -1}}
            )

            if update_res.modified_count > 0:
                transactions_col.insert_one({
                    "shipment_id": tracking_found,
                    "sku": sku_found,
                    "location": selected_loc,
                    "type": "outbound",
                    "timestamp": datetime.now()
                })
                st.session_state.last_msg = ("success", f"✅ Shipped: {sku_found}")
            else:
                st.session_state.last_msg = ("error", f"❌ Error: {sku_found} out of stock at {selected_loc}")
            
            # Reset buffer for next transaction
            st.session_state.scan_buffer = []
        
        # CLEAR the input widget value for the next scan
        st.session_state.main_scanner = ""

# --- 4. APP CONFIG & SESSION STATE INITIALIZATION ---
st.set_page_config(page_title="Beck's High-Speed WMS", layout="wide")

if "scan_buffer" not in st.session_state:
    st.session_state.scan_buffer = []
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
if st.sidebar.button("📥 Inbound (Scan In)", use_container_width=True):
    st.session_state.page = "inbound"

# --- 6. PAGE ROUTING ---

# HOME PAGE
if st.session_state.page == "home":
    st.title("📦 Warehouse Dashboard")
    total_items = inventory_col.count_documents({})
    low_stock = inventory_col.count_documents({"quantity": {"$lt": 5}})
    c1, c2 = st.columns(2)
    c1.metric("Unique SKUs", total_items)
    c2.metric("Low Stock Alerts", low_stock)

# OUTBOUND PAGE (The Scan Flow)
elif st.session_state.page == "outbound":
    st.title("📤 Outbound Scan Center")
    
    all_locs = inventory_col.distinct("location")
    st.session_state.current_loc = st.selectbox(
        "Step 1: Set Your Picking Location", 
        options=all_locs, 
        index=None,
        placeholder="Select location to enable scanner..."
    )

    if st.session_state.current_loc:
        st.divider()
        
        # Display Messages (Success/Error) from previous scan
        msg_type, msg_text = st.session_state.last_msg
        if msg_type == "success": st.success(msg_text)
        if msg_type == "error": st.error(msg_text)

        # UI Visual Cues
        if not st.session_state.scan_buffer:
            st.info("🎯 **ACTION:** Scan Item SKU")
        else:
            st.warning(f"📦 **SKU RECORDED:** {st.session_state.scan_buffer[0]} | **NEXT:** Scan Shipment Tracking")

        # THE SCAN ZONE (The only input field used)
        st.text_input(
            "SCAN_ZONE", 
            key="main_scanner", 
            on_change=process_scan, # This function runs EVERY time the scanner hits Enter
            label_visibility="collapsed"
        )

        auto_focus_js()

        # Transaction History Table
        st.subheader("Recent Activity")
        logs = list(transactions_col.find().sort("timestamp", -1).limit(5))
        if logs:
            df_logs = pd.DataFrame(logs)
            st.table(df_logs[['timestamp', 'sku', 'shipment_id', 'location']])

# INBOUND PAGE
elif st.session_state.page == "inbound":
    st.title("📥 Inbound Receiving")
    st.write("Inbound scanning logic coming soon...")

# --- 7. GLOBAL INVENTORY VIEW (Always at bottom) ---
st.divider()
st.subheader("📊 Live Inventory Status")
inventory_data = list(inventory_col.find({}, {"_id": 0}))

if inventory_data:
    df = pd.DataFrame(inventory_data)
    st.dataframe(df, use_container_width=True)
    
    st.write("### 📂 Export Data")
    col_exp1, col_exp2 = st.columns(2)
    file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with col_exp1:
        tx_data = list(transactions_col.find({"type": "outbound"}, {"_id": 0}))
        if tx_data:
            df_tx = pd.DataFrame(tx_data)
            st.download_button("📥 Export Transactions", data=to_excel(df_tx), file_name=f"tx_{file_ts}.xlsx")
    
    with col_exp2:
        st.download_button("📥 Export Inventory", data=to_excel(df), file_name=f"inv_{file_ts}.xlsx")