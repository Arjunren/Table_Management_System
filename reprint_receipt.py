import os
from datetime import datetime

def generate_official_receipt_reprint_text(
    txn, items, subtotal, discount, sc, vatable, vat,
    grand_total, payment, cashier_name,
    split_data=None, all_splits=None
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    table_name = txn.get('assigned_tables') if txn.get('assigned_tables') else "No Table"
    txn_code = txn.get('transaction_code', 'UNKNOWN_TXN')

    cut_command = "\x1d\x56\x41\x03"

    def build_copy(copy_type):
        receipt = []
        receipt.append("========================================")
        receipt.append("              RESTO  BAR                ")
        receipt.append("  Rizal Mabini Street Purok Pag-asa,    ")
        receipt.append("    Brgy. Port Balton 5309 San Vicente  ")
        receipt.append("          Palawan, Philippines          ")
        receipt.append("    VAT Reg. TIN: 681-911-330-000       ")
        receipt.append("========================================")
        receipt.append(f"   OFFICIAL RECEIPT - {copy_type}   ")
        receipt.append("----------------------------------------")
        receipt.append(f"Txn Code : {txn_code}")
        receipt.append(f"Date/Time: {now}")
        receipt.append(f"Cashier  : {cashier_name}")
        receipt.append(f"Table    : {table_name}")
        receipt.append(f"Guest    : {txn.get('guest_name', 'Guest')}")
        receipt.append("----------------------------------------")
        receipt.append(f"{'QTY':<4} {'ITEM':<20} {'AMOUNT':>13}")
        receipt.append("----------------------------------------")

        for item in items:
            name = item.get('menu_name', 'Item')[:20]
            qty = item.get('quantity', 1)
            total = item.get('total_price', 0.0)
            receipt.append(f"{qty:<4} {name:<20} {total:>13.2f}")

        receipt.append("----------------------------------------")
        receipt.append(f"{'Subtotal:':<25} {subtotal:>14.2f}")

        if discount > 0 and not split_data:
            receipt.append(f"{'LESS DISCOUNT:':<25} -{discount:>13.2f}")

        receipt.append(f"{'Service Charge (10%):':<25} {sc:>14.2f}")
        receipt.append(f"{'VATable Sales:':<25} {vatable:>14.2f}")
        receipt.append(f"{'VAT (12%):':<25} {vat:>14.2f}")

        receipt.append("----------------------------------------")
        receipt.append(f"GRAND TOTAL:              {grand_total:>14.2f}")
        receipt.append("========================================")

        if split_data:
            receipt.append("         SPLIT BILL SUMMARY             ")
            receipt.append("----------------------------------------")

            if all_splits:
                receipt.append("Bill Shared By:")
                for sp in all_splits:
                    sp_name = sp.get('split_name', 'Guest')[:20]
                    sp_amt = float(sp.get('amount', 0))
                    receipt.append(f"  {sp_name:<20} {sp_amt:>14.2f}")

                receipt.append("----------------------------------------")

            split_type = split_data.get('split_type', '').upper()
            split_name = split_data.get('split_name', 'Split Payment')
            split_amount = float(split_data.get('amount', 0.0))
            split_items = split_data.get('split_items', [])

            receipt.append("This Receipt belongs to :")
            receipt.append(f">> {split_name}")
            receipt.append(f"Split Method : By {split_type}")
            
            if split_type == 'ITEMS' and split_items:
                receipt.append("----------------------------------------")
                receipt.append("Items covered in this split:")
                for s_item in split_items:
                    s_name = s_item.get('menu_name', 'Item')[:20]
                    s_qty = s_item.get('quantity', 1)
                    s_total = float(s_item.get('total_price', 0.0))
                    receipt.append(f"{s_qty:<4} {s_name:<20} {s_total:>13.2f}")
                receipt.append("----------------------------------------")

            receipt.append(f"Net Payable  :            {split_amount:>14.2f}")
            receipt.append("========================================")

        receipt.append(f"{'Amount Tendered:':<25} {payment.get('tendered', 0.0):>14.2f}")
        receipt.append(f"{'Change:':<25} {payment.get('change', 0.0):>14.2f}")
        receipt.append(f"{'Payment Method:':<25} {payment.get('method', 'CASH').upper():>14}")

        ref_num = payment.get('reference_number')
        if ref_num and str(ref_num).strip().upper() not in ['N/A', 'NONE', '']:
            short_ref = str(ref_num).strip()[:14]
            receipt.append(f"{'Ref No:':<25} {short_ref:>14}")

        receipt.append("========================================")
        receipt.append("         *** REPRINT COPY ***           ")
        receipt.append("       Thank you for visiting us!       ")
        receipt.append("========================================")

        return "\n".join(receipt)

    cashier_copy = build_copy("CASHIER COPY") + "\n\n\n\n\n" + cut_command
    customer_copy = build_copy("CUSTOMER COPY") + "\n\n\n\n\n" + cut_command

    final_receipt_text = cashier_copy + customer_copy

    # try:
    #     folder_name = "Reprint"
    #     os.makedirs(folder_name, exist_ok=True)

    #     safe_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    #     filename = f"OR_REPRINT_{txn_code}_{safe_time}.txt"
    #     file_path = os.path.join(folder_name, filename)

    #     with open(file_path, 'w', encoding='utf-8') as file:
    #         file.write(final_receipt_text)

    # except Exception as e:
    #     print(f"Error saving receipt file: {e}")

    return final_receipt_text