import streamlit as st
from pymongo import MongoClient

from wms.config import get_mongo_uri


@st.cache_resource
def init_connection() -> MongoClient:
    """Initialize and cache the MongoDB client.

    Uses env var `MONGO_URI` (preferred for local development) and falls back
    to `st.secrets["mongo_uri"]`.
    """
    try:
        uri = get_mongo_uri(required=True)
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
        "mm": db["MM"],
        "locations": db["Locations"],
        "transactions": db["transactions"],
        "movement": db["movement"],
        "users": db["users"],
    }
