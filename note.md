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

@st.cache_resource
def init_connection():
try: # Hardcoded local connection for performance and reliability
client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
client.server_info()
return client
except Exception as e:
st.error("Connection Error: Local MongoDB not detected. Please ensure MongoDB service is running.")
st.stop()
return None
