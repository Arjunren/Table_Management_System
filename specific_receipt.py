import os
from datetime import datetime

def generate_specific_receipt_text(txn, items, printer_name):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    table_name = txn.get('assigned_tables', "No Table")
    txn_code = txn.get('transaction_code', 'UNKNOWN_TXN')
    guest_name = txn.get('guest_name', 'Guest')
    
    receipt = []
    receipt.append("========================================")
    receipt.append(f"{printer_name + ' ORDERS':^40}")
    receipt.append("========================================")
    receipt.append(f"Table : {table_name}")
    receipt.append(f"Guest : {guest_name}")
    receipt.append(f"Time  : {now}")
    receipt.append(f"Txn   : {txn_code}")
    receipt.append("----------------------------------------")
    receipt.append(f"{'QTY':<4} {'ITEM':<35}")
    receipt.append("----------------------------------------")
    
    for item in items:
        name = item.get('menu_name', 'Item')[:35]
        qty = item.get('quantity', 1)
        status = item.get('status', 'pending')
        item_type = item.get('type', 'solid')
        item_note = item.get('note', '') # Grab note

        receipt.append(f"{qty:<4} {name}")
        
        if item_note:
            receipt.append(f"     *Note: {item_note}")
        
        if item_type == 'solid':
            if status == 'preparing':
                receipt.append("     >> OPEN FIRE <<")
            else:
                receipt.append("     >> WAIT TO FIRE <<")
        
        receipt.append("") # Blank space for easy reading
    receipt.append("----------------------------------------")
    receipt.append("             END OF ORDER               ")
    receipt.append("========================================\n\n\n\n\n\n")
    receipt_text = "\n".join(receipt)

    try:
        folder_name = "specific_receipts"
        os.makedirs(folder_name, exist_ok=True)
        safe_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{printer_name}_{txn_code}_{safe_time}.txt"
        file_path = os.path.join(folder_name, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(receipt_text)
    except Exception as e:
        print(f"Error saving specific receipt: {e}")
        
    cut_command = "\x1d\x56\x00"
    return receipt_text + cut_command