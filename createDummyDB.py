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
        # Test connection
        client.server_info()
        print("✅ Successfully connected to MongoDB.")
    except Exception as e:
        print(f"❌ Could not connect to MongoDB: {e}")
        return

    # 2. Create/Select Database
    db = client["warehouse_db"]
    
    # 3. Define Collections
    inventory = db["inventory"]
    transactions = db["transactions"]

    # 4. Clear existing data (Optional: only if you want a fresh start)
    inventory.delete_many({})
    transactions.delete_many({})
    print("🧹 Cleared old data.")

    # 5. Insert Sample Inventory Data
    sample_items = [
        {"sku": "SKU001", "name": "Wireless Mouse", "quantity": 50, "location": "Home1"},
        {"sku": "SKU002", "name": "Mechanical Keyboard", "quantity": 25, "location": "Home2"},
        {"sku": "SKU001", "name": "Wireless Mouse", "quantity": 50, "location": "WHS1"},
        {"sku": "SKU003", "name": "USB-C Cable", "quantity": 100, "location": "WHS1"},
        {"sku": "690123456789", "name": "Demo Box", "quantity": 10, "location": "WHS1"}
    ]

    inventory.insert_many(sample_items)
    print(f"📦 Inserted {len(sample_items)} sample items into inventory.")

    # 6. Create Indexes (This makes searching for SKUs lightning fast)
    inventory.create_index([("sku", pymongo.ASCENDING)], unique=True)
    print("⚡ Created unique index on SKU field.")

    print("\n--- Setup Complete ---")
    print("You can now test your WMS app with SKU: SKU001")

if __name__ == "__main__":
    setup_database()