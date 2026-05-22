import os
from datetime import datetime

def generate_free_receipt_text(txn, items, subtotal, sc, vatable, vat, grand_total, manager_name):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    table_name = txn.get('assigned_tables') if txn.get('assigned_tables') else "No Table"
    txn_code = txn.get('transaction_code', 'UNKNOWN_TXN')

    # ESC/POS Cut Command
    cut_command = "\x1d\x56\x00"

    def build_copy(copy_type):
        receipt = []

        receipt.append("========================================")
        receipt.append("               RESTO  BAR               ")
        receipt.append("  Sitio Barongbong, Brgy. Port Balton   ")
        receipt.append(" 5309 San Vicente, Palawan, Philippines ")
        receipt.append("    VAT Reg. TIN: 669-176-884-00000     ")
        receipt.append("========================================")
        receipt.append(f"     *** FOC - {copy_type} *** ")
        receipt.append("----------------------------------------")
        receipt.append(f"Txn Code : {txn_code}")
        receipt.append(f"Date/Time: {now}")
        receipt.append(f"Auth By  : {manager_name}")
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
        receipt.append(f"{'Service Charge (10%):':<25} {sc:>14.2f}")
        receipt.append(f"{'VATable Sales:':<25} {vatable:>14.2f}")
        receipt.append(f"{'VAT (12%):':<25} {vat:>14.2f}")
        receipt.append("----------------------------------------")
        receipt.append(f"{'Total Covered:':<25} {grand_total:>14.2f}")
        receipt.append(f"{'AMOUNT PAID:':<25} {'0.00':>14}")
        receipt.append("========================================")
        receipt.append("           COMPLIMENTARY COPY           ")
        receipt.append("========================================")

        return "\n".join(receipt)

    # Add cut after EACH copy
    cashier_copy = build_copy("CASHIER COPY") + cut_command
    customer_copy = build_copy("CUSTOMER COPY") + "\n\n\n\n\n\n" + cut_command

    final_receipt_text = cashier_copy + "\n\n\n" + customer_copy

    try:
        folder_name = "free_receipts"
        os.makedirs(folder_name, exist_ok=True)

        safe_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"FOC_{txn_code}_{safe_time}.txt"
        file_path = os.path.join(folder_name, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(final_receipt_text)

    except Exception as e:
        print(f"Error saving free receipt file: {e}")

    return final_receipt_text