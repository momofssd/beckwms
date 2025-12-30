import streamlit as st
from pymongo import MongoClient


@st.cache_resource
def init_connection() -> MongoClient:
    """Initialize and cache the MongoDB client.

    Uses `st.secrets["mongo_uri"]`.
    """
    try:
        uri = st.secrets["mongo_uri"]
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client
    except Exception:
        st.error("Connection Error: Could not connect to MongoDB Atlas cluster.")
        st.stop()
        raise


def get_collections():
    client = init_connection()
    db = client["warehouse_db"]
    return {
        "inventory": db["inventory"],
        "transactions": db["transactions"],
        "users": db["users"],
    }

