import os
from datetime import datetime

def generate_void_receipt_text(item_info, void_qty, reason, cashier_name, manager_name, printer_copy_name):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    table_name = item_info.get('table_name') if item_info.get('table_name') else "No Table"
    txn_code = item_info.get('transaction_code', 'UNKNOWN_TXN')
    guest_name = item_info.get('guest_name', 'Guest')
    item_name = item_info.get('menu_name', 'Item')
    
    receipt = []
    receipt.append("========================================")
    receipt.append(f"{'*** VOID TICKET ***':^40}")
    receipt.append(f"{'[' + printer_copy_name + ' COPY]':^40}")
    receipt.append("========================================")
    receipt.append(f"Date/Time: {now}")
    receipt.append(f"Txn Code : {txn_code}")
    receipt.append(f"Table    : {table_name}")
    receipt.append(f"Guest    : {guest_name}")
    receipt.append("----------------------------------------")
    receipt.append("ITEM VOIDED:")
    receipt.append(f" -> {void_qty}x {item_name}")
    receipt.append("REASON:")
    receipt.append(f" -> {reason}")
    receipt.append("----------------------------------------")
    receipt.append(f"Cashier  : {cashier_name}")
    receipt.append(f"Auth By  : {manager_name} (Manager)")
    receipt.append("========================================\n\n\n\n\n\n")
    
    receipt_text = "\n".join(receipt)
    
    try:
        folder_name = "void_receipts"
        os.makedirs(folder_name, exist_ok=True)
        safe_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"VOID_{printer_copy_name}_{txn_code}_{safe_time}.txt"
        file_path = os.path.join(folder_name, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(receipt_text)
    except Exception as e:
        print(f"Error saving void receipt: {e}")
        
    cut_command = "\x1d\x56\x00"
    return receipt_text + cut_command