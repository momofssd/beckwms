import os
import pymongo
from dotenv import load_dotenv

# 1. Load environment variables from .env file
load_dotenv()
mongo_uri = os.getenv("MONGO_URI")

def clone_database(source_db_name, target_db_name):
    try:
        # 2. Connect to MongoDB Atlas
        client = pymongo.MongoClient(mongo_uri)
        
        source_db = client[source_db_name]
        target_db = client[target_db_name]

        # 3. Get list of all collections in the source database
        collections = source_db.list_collection_names()
        
        print(f"Starting clone from {source_db_name} to {target_db_name}...")

        for col_name in collections:
            # Skip system collections
            if col_name.startswith("system."):
                continue
                
            print(f"Cloning collection: {col_name}")
            
            # Fetch all documents from the source collection
            documents = list(source_db[col_name].find())
            
            if documents:
                # Insert documents into the target collection
                target_db[col_name].insert_many(documents)
            else:
                # If collection is empty, just create it
                target_db.create_collection(col_name)

        print("Database cloning completed successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client.close()

# Execute the clone
if __name__ == "__main__":
    clone_database("warehouse_db", "warehouse_db_copy")