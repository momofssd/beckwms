import streamlit as st
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

# Helper function to convert Dataframe to Excel bytes
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# --- 2. APP CONFIG & SESSION STATE ---
st.set_page_config(page_title="Beck's WMS", layout="wide")

if "page" not in st.session_state:
    st.session_state.page = "home"

# --- 3. SIDEBAR NAVIGATION ---
st.sidebar.title("WMS Control Panel")
if st.sidebar.button("🏠 Home", use_container_width=True):
    st.session_state.page = "home"
if st.sidebar.button("📤 Outbound (Scan Out)", use_container_width=True):
    st.session_state.page = "outbound"
if st.sidebar.button("📥 Inbound (Scan In)", use_container_width=True):
    st.session_state.page = "inbound"

# --- 4. HOME PAGE ---
if st.session_state.page == "home":
    st.title("📦 Warehouse Dashboard")
    st.write("Welcome to your fulfillment management system. Select a task from the sidebar.")
    
    total_items = inventory_col.count_documents({})
    low_stock = inventory_col.count_documents({"quantity": {"$lt": 5}})
    
    c1, c2 = st.columns(2)
    c1.metric("Unique SKUs", total_items)
    c2.metric("Low Stock Alerts", low_stock, delta_color="inverse")

# --- 5. OUTBOUND LOGIC ---
elif st.session_state.page == "outbound":
    st.title("📤 Outbound Processing")
    
    col_form, col_history = st.columns([1, 1])

    with col_form:
        st.subheader("Process Outbound")
        
        # Step 1: Select Location first (Fetched from all available locations in DB)
        all_db_locations = inventory_col.distinct("location")
        
        selected_location = st.selectbox(
            "Step 1: Select Picking Location", 
            options=all_db_locations,
            index=None,
            placeholder="Choose a location..."
        )

        # Step 2: Show Scan Form only after Location is selected
        if selected_location:
            with st.form("outbound_form", clear_on_submit=True):
                item_sku = st.text_input("Step 2: Scan Item Barcode (SKU)")
                shipment_id = st.text_input("Step 3: Scan Shipment Tracking") 
                
                submit = st.form_submit_button("Confirm Shipment Out")

                if submit:
                    if item_sku and shipment_id:
                        # Verify SKU exists at the chosen location
                        item_at_loc = inventory_col.find_one({
                            "sku": item_sku, 
                            "location": selected_location
                        })
                        
                        if item_at_loc:
                            if item_at_loc.get("quantity", 0) > 0:
                                # DEDUCT -1
                                inventory_col.update_one(
                                    {"sku": item_sku, "location": selected_location},
                                    {"$inc": {"quantity": -1}}
                                )
                                
                                # LOG TRANSACTION
                                transactions_col.insert_one({
                                    "shipment_id": shipment_id,
                                    "sku": item_sku,
                                    "location": selected_location,
                                    "type": "outbound",
                                    "timestamp": datetime.now()
                                })
                                st.success(f"✅ SKU: {item_sku} removed from {selected_location}")
                                st.rerun()
                            else:
                                st.error(f"❌ Error: Out of stock for {item_sku} at {selected_location}")
                        else:
                            st.warning(f"❓ SKU {item_sku} not found at {selected_location}")
                    else:
                        st.error("Please scan both SKU and Shipment Tracking.")
        else:
            st.info("Waiting for location selection...")

    with col_history:
        st.subheader("Recent Activity")
        recent = list(transactions_col.find().sort("timestamp", -1).limit(5))
        if recent:
            for r in recent:
                loc_str = f" from **{r.get('location', 'N/A')}**"
                st.write(f"🕒 {r['timestamp'].strftime('%H:%M:%S')} - **{r['sku']}**{loc_str} shipped on **{r['shipment_id']}**")
        else:
            st.write("No scans in this session yet.")

# --- 6. INBOUND LOGIC ---
elif st.session_state.page == "inbound":
    st.title("📥 Inbound Receiving")
    st.info("Inbound module logic placeholder.")

# --- 7. GLOBAL INVENTORY VIEW & EXPORTS ---
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
            df_tx = df_tx.rename(columns={"timestamp": "time stamp", "shipment_id": "shipment tracking"})
            df_tx["outbound qty"] = 1
            cols_tx = ["time stamp", "sku", "location", "shipment tracking", "outbound qty"]
            df_tx = df_tx[[c for c in cols_tx if c in df_tx.columns]]
            df_tx["time stamp"] = df_tx["time stamp"].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            st.download_button(
                label="📥 Export Transactions to Excel",
                data=to_excel(df_tx),
                file_name=f"transactions_{file_ts}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.button("Export Transactions to Excel", disabled=True, use_container_width=True)

    with col_exp2:
        df_inv_exp = df.copy()
        df_inv_exp = df_inv_exp.rename(columns={"quantity": "qty"})
        cols_inv = ["sku", "name", "qty", "location"]
        df_inv_exp = df_inv_exp[[c for c in cols_inv if c in df_inv_exp.columns]]
        
        st.download_button(
            label="📥 Export Inventory to Excel",
            data=to_excel(df_inv_exp),
            file_name=f"inventory_{file_ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
else:
    st.write("Inventory is currently empty.")