import pymongo
from pymongo import MongoClient
import sys
import io

# Forces the terminal output to handle Unicode characters even on GBK systems
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def setup_database():
    # 1. Connect to MongoDB
    try:
        client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
        client.server_info()
        print("✅ Successfully connected to MongoDB.")
    except Exception as e:
        print(f"❌ Could not connect to MongoDB: {e}")
        return

    db = client["warehouse_db"]
    inventory = db["inventory"]
    transactions = db["transactions"]

    # 4. Clear existing data and indices for a fresh start
    # We must drop the old index because it was "SKU only"
    inventory.drop_indexes()
    inventory.delete_many({})
    transactions.delete_many({})
    print("🧹 Cleared old data and indices.")

    # 5. Insert Sample Inventory Data
    # SKU001 now exists in both Home1 and WHS1
    sample_items = [
        {"sku": "SKU001", "name": "Wireless Mouse", "quantity": 50, "location": "Home1"},
        {"sku": "SKU002", "name": "Mechanical Keyboard", "quantity": 25, "location": "Home2"},
        {"sku": "SKU001", "name": "Wireless Mouse", "quantity": 50, "location": "WHS1"},
        {"sku": "SKU003", "name": "USB-C Cable", "quantity": 100, "location": "WHS1"},
        {"sku": "690123456789", "name": "Demo Box", "quantity": 10, "location": "WHS1"}
    ]

    inventory.insert_many(sample_items)
    print(f"📦 Inserted {len(sample_items)} sample items into inventory.")

    # 6. Create COMPOUND INDEX
    # This allows SKU001 to exist in multiple locations, 
    # but prevents having two entries for SKU001 in the SAME location.
    inventory.create_index([("sku", pymongo.ASCENDING), ("location", pymongo.ASCENDING)], unique=True)
    print("⚡ Created unique compound index on [SKU + Location].")

    print("\n--- Setup Complete ---")
    print("You can now test your WMS app. Scanning SKU001 will now show two location options.")

if __name__ == "__main__":
    setup_database()