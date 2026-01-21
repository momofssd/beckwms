"""Movement deletion helper with cascade delete of related transactions."""

from typing import Optional


def delete_movement_with_transactions(
    *, movement_col, transactions_col, inventory_col, transaction_num: str
) -> tuple[bool, str]:
    """
    Delete a movement and all its related transactions, and reverse inventory changes.
    
    Args:
        movement_col: MongoDB movement collection
        transactions_col: MongoDB transactions collection
        inventory_col: MongoDB inventory collection
        transaction_num: The movement transaction number to delete
    
    Returns:
        tuple: (success: bool, message: str)
    """
    # Find the movement document
    movement = movement_col.find_one({"transaction_num": transaction_num})
    
    if not movement:
        return False, f"Movement {transaction_num} not found."
    
    movement_type = str(movement.get("movement_type", "")).strip().lower()
    details = movement.get("details", [])
    
    if not isinstance(details, list):
        return False, "Invalid movement details format."
    
    # Reverse inventory changes based on movement type
    try:
        for detail in details:
            if not isinstance(detail, dict):
                continue
            
            sku = str(detail.get("sku", "")).strip().upper()
            location = str(detail.get("location", "")).strip().upper()
            
            if movement_type == "inbound":
                # Reverse inbound: decrement inventory
                qty = int(detail.get("inbound_qty", 0) or 0)
                if qty > 0:
                    inventory_col.update_one(
                        {"sku": sku, "location": location},
                        {"$inc": {"quantity": -qty}},
                    )
            
            elif movement_type == "outbound":
                # Reverse outbound: increment inventory
                qty = int(detail.get("outbound_qty", 0) or 0)
                if qty > 0:
                    inventory_col.update_one(
                        {"sku": sku, "location": location},
                        {"$inc": {"quantity": qty}},
                        upsert=True,
                    )
            
            elif movement_type == "void":
                # Reverse void: increment inventory (restore voided quantity)
                qty = int(detail.get("void_qty", 0) or 0)
                if qty > 0:
                    inventory_col.update_one(
                        {"sku": sku, "location": location},
                        {"$inc": {"quantity": qty}},
                        upsert=True,
                    )
            
            elif movement_type == "sto":
                # Reverse STO: move inventory back from destination to source
                qty = int(detail.get("qty", 0) or 0)
                location_from = str(detail.get("location_from", "")).strip().upper()
                location_to = str(detail.get("location_to", "")).strip().upper()
                
                if qty > 0 and location_from and location_to:
                    # Decrement from destination
                    inventory_col.update_one(
                        {"sku": sku, "location": location_to},
                        {"$inc": {"quantity": -qty}},
                    )
                    # Increment at source
                    inventory_col.update_one(
                        {"sku": sku, "location": location_from},
                        {"$inc": {"quantity": qty}},
                        upsert=True,
                    )
        
        # Delete all related transactions
        delete_result = transactions_col.delete_many(
            {"movement_transaction_num": transaction_num}
        )
        
        # Delete the movement document
        movement_col.delete_one({"transaction_num": transaction_num})
        
        return True, f"Movement {transaction_num} deleted successfully. {delete_result.deleted_count} transaction(s) removed and inventory reversed."
    
    except Exception as e:
        return False, f"Error deleting movement: {str(e)}"
