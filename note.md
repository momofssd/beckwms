python -m streamlit run app.py

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
