import os
from datetime import datetime

def generate_pre_receipt_text(txn, items, subtotal, service_charge, grand_total):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    table_name = txn.get('assigned_tables') if txn.get('assigned_tables') else "No Table"
    txn_code = txn.get('transaction_code', 'UNKNOWN_TXN')
    
    receipt = []
    receipt.append("========================================")
    receipt.append("               RESTO  BAR               ")
    receipt.append("========================================")
    receipt.append("          PRE-BILL ASSESSMENT           ")
    receipt.append("----------------------------------------")
    receipt.append(f"Txn Code : {txn_code}")
    receipt.append(f"Date/Time: {now}")
    receipt.append(f"Table    : {table_name}")
    receipt.append(f"Guest    : {txn.get('guest_name', 'Guest')}")
    receipt.append("----------------------------------------")
    receipt.append(f"{'QTY':<4} {'ITEM':<20} {'AMOUNT':>13}")
    receipt.append("----------------------------------------")
    for item in items:
        name = item.get('menu_name', 'Item')[:20]
        qty = item.get('quantity', 1)
        total = float(item.get('total_price', 0.0))
        receipt.append(f"{qty:<4} {name:<20} {total:>13.2f}")

    receipt.append("----------------------------------------")
    receipt.append(f"{'Subtotal:':<25} {subtotal:>14.2f}")
    receipt.append(f"{'Service Charge (10%):':<25} {service_charge:>14.2f}")
    vatable = subtotal / 1.12
    vat = subtotal - vatable
    receipt.append(f"{'VATable Sales:':<25} {vatable:>14.2f}")
    receipt.append(f"{'VAT (12%):':<25} {vat:>14.2f}")
    receipt.append("----------------------------------------")
    receipt.append(f"GRAND TOTAL:              {grand_total:>14.2f}")
    receipt.append("========================================")
    receipt.append("    THIS IS NOT AN OFFICIAL RECEIPT     ")
    receipt.append("========================================\n\n\n\n\n\n")
    
    receipt_text = "\n".join(receipt)
    
    try:
        folder_name = "pre_receipts"
        os.makedirs(folder_name, exist_ok=True)
        
        safe_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"PRE_{txn_code}_{safe_time}.txt"
        file_path = os.path.join(folder_name, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(receipt_text)
            
    except Exception as e:
        print(f"Error saving pre-receipt file: {e}")
        
    cut_command = "\x1d\x56\x00"
    return receipt_text + cut_command