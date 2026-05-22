import socket
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, send_from_directory
from dotenv import load_dotenv
from pre_receipt import generate_pre_receipt_text
from free_receipt import generate_free_receipt_text
from official_receipt import generate_official_receipt_text
from specific_receipt import generate_specific_receipt_text
from void_receipt import generate_void_receipt_text
from reprint_receipt import generate_official_receipt_reprint_text
import mysql.connector
from flask_cors import CORS
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = mysql.connector.connect(
        host=os.environ.get('MYSQL_HOST', 'localhost'),
        user=os.environ.get('MYSQL_USER', 'root'),
        password=os.environ.get('MYSQL_PASSWORD', ''),
        database=os.environ.get('MYSQL_DB', 'datatelcom_tms')
    )
    cursor = conn.cursor(dictionary=True)
    return conn, cursor

def get_service_charge_rate():
    try:
        conn, cursor = get_db()
        cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'service_charge_rate'")
        row = cursor.fetchone()
        cursor.close()
        if row and row['setting_value']:
            return float(row['setting_value'])
    except Exception as e:
        print(f"Error fetching service charge: {e}")
    return 0.00

load_dotenv()

app = Flask(__name__)
CORS(app)

app.secret_key = os.environ.get('SECRET_KEY')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'datatelcom_tms')

def print_to_escpos(text_data, printer_ip):
    if not printer_ip:
        print("--------------------------------------------------")
        print("PRINT ERROR: Printer IP not found in database! Cannot print.")
        print("--------------------------------------------------")
        return False
        
    try:
        print("--------------------------------------------------")
        print(f"PRINT STATUS: Attempting to connect to printer at IP: {printer_ip} (Port 9100)...")
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect((printer_ip, 9100))
            
            s.sendall(b'\x1b\x40')
            s.sendall(text_data.encode('utf-8'))
            s.sendall(b'\x1d\x56\x00')
            
            print(f"PRINT SUCCESS: Receipt successfully sent and printed at {printer_ip}!")
            print("--------------------------------------------------")
            return True
            
    except Exception as e:
        print(f"PRINT FAILED: Could not connect or print to {printer_ip}.")
        print(f"ERROR DETAILS: {e}")
        print("--------------------------------------------------")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/floatingbar/login', methods=['POST'])
def login():
    data = request.get_json()
    employee_id = data.get('employee_id')
    password = data.get('password', '')

    conn, cursor = get_db()
    
    cursor.execute('SELECT * FROM employee_management WHERE employee_id = %s', (employee_id,))
    account = cursor.fetchone()

    if account:
        if account['position'] == 'waiter':
            pass 
        elif account['position'] == 'manager':
            if account['password'] != password:
                return jsonify({'success': False, 'message': 'Please try again.'}), 401
        elif account['position'] == 'cashier':
            if account['password'] != password:
                return jsonify({'success': False, 'message': 'Please try again.'}), 401
            
            cursor.execute("SELECT id FROM cash_drawer WHERE employee_id = %s AND status = 'open' LIMIT 1", (account['id'],))
            active_shift = cursor.fetchone()
            
            if not active_shift:
                return jsonify({'success': False, 'message': 'Login denied: You do not have an open shift. Please ask your manager to open your shift first.'}), 401
        else:
            return jsonify({'success': False, 'message': 'Invalid role configuration.'}), 401

        session['loggedin'] = True
        session['id'] = account['id']
        session['employee_id'] = account['employee_id']
        session['role'] = account['position']
        session['name'] = f"{account['firstName']} {account['lastName']}"

        if account['position'] == 'cashier':
            redirect_url = url_for('cashier_dashboard')
        elif account['position'] == 'waiter':
            redirect_url = url_for('waiter_management')
        elif account['position'] == 'manager':
            redirect_url = url_for('manager_dashboard')
        else:
            redirect_url = url_for('index')

        return jsonify({'success': True, 'position': account['position'], 'name': session['name'], 'redirect_url': redirect_url})
    
    return jsonify({'success': False, 'message': 'Employee ID not found.'}), 401

@app.route('/cashier')
def cashier_dashboard():
    if session.get('role') == 'cashier':
        cashier_id = session.get('id')
        conn, cursor = get_db()
        
        cursor.execute("SELECT id FROM cash_drawer WHERE employee_id = %s AND status = 'open' LIMIT 1", (cashier_id,))
        active_shift = cursor.fetchone()
        shift_status = 'Open' if active_shift else 'Closed'
        
        cursor.execute('''
            SELECT t.id, t.transaction_code, t.guest_name, t.contact_number, 
                   t.guest_email, t.guest_count, t.status, t.created_at,
                   GROUP_CONCAT(tb.table_name SEPARATOR ', ') as assigned_tables
            FROM transactions t
            LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
            LEFT JOIN tables tb ON tt.table_id = tb.id
            WHERE t.status = 'open'
            GROUP BY t.id ORDER BY t.created_at DESC
        ''')
        active_transactions = cursor.fetchall()
        
        total_guests = sum(txn['guest_count'] for txn in active_transactions if txn['guest_count'])
        main_deck_count = sum(1 for txn in active_transactions if txn['assigned_tables'] and 'Table' in txn['assigned_tables'])
        
        cursor.close()

        return render_template('cashier.html', transactions=active_transactions, total_guests=total_guests, main_deck_count=main_deck_count, shift_status=shift_status)
    return redirect(url_for('index'))

@app.route('/waiter')
def waiter_management():
    if session.get('role') == 'waiter':
        return render_template('waiter.html') 
    return redirect(url_for('index'))

@app.route('/api/transaction/<int:tx_id>', methods=['GET'])
def get_transaction_details(tx_id):
    try:
        conn, cursor = get_db()
        cursor.execute('''
            SELECT o.id, o.quantity, o.unit_price, o.total_price, o.status, o.void_reason, o.note, o.waiter_name, m.menu_name 
            FROM order_items o 
            JOIN main_menu_management m ON o.menu_id = m.menu_id 
            WHERE o.transaction_id = %s
        ''', (tx_id,))
        items = cursor.fetchall()

        for item in items:
            item['unit_price'] = float(item['unit_price'])
            item['total_price'] = float(item['total_price'])

        subtotal = sum(item['total_price'] for item in items if item.get('status') != 'void')
        service_charge = subtotal * get_service_charge_rate()
        grand_total = subtotal + service_charge

        cursor.execute('''
            SELECT t.transaction_code, t.guest_name, 
                   GROUP_CONCAT(tb.table_name SEPARATOR ', ') as assigned_tables
            FROM transactions t
            LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
            LEFT JOIN tables tb ON tt.table_id = tb.id
            WHERE t.id = %s
            GROUP BY t.id
        ''', (tx_id,))
        txn = cursor.fetchone()

        cursor.execute("SELECT guest_name FROM transaction_guests WHERE transaction_id = %s", (tx_id,))
        additional_guests_rows = cursor.fetchall()
        all_guests = [txn['guest_name']] if txn else ['Guest']
        for row in additional_guests_rows:
            all_guests.append(row['guest_name'])

        if not txn:
            return jsonify({'success': False, 'message': 'Transaction not found'}), 404

        return jsonify({
            'success': True,
            'transaction': txn,
            'items': items,
            'subtotal': round(subtotal, 2),
            'service_charge': round(service_charge, 2),
            'grand_total': round(grand_total, 2),
            'all_guests': all_guests
        })
    except Exception as e:
        print(f"Error fetching transaction details: {e}")
        return jsonify({'success': False, 'message': 'Database error'}), 500
    finally:
        cursor.close()

@app.route('/api/authorize_manager', methods=['POST'])
def authorize_manager():
    password = request.get_json().get('password')
    conn, cursor = get_db()
    cursor.execute("SELECT firstName, lastName FROM employee_management WHERE password = %s AND position = 'manager'", (password,))
    manager = cursor.fetchone()
    cursor.close()
    
    if manager:
        return jsonify({'success': True, 'manager_name': f"{manager['firstName']} {manager['lastName']}"})
    return jsonify({'success': False, 'message': 'Invalid Manager Password'})

@app.route('/api/void_item', methods=['POST'])
def void_item():
    data = request.json
    item_id = data.get('item_id')
    password = data.get('password')
    reason = data.get('reason')
    void_qty = int(data.get('void_qty', 1))
    cashier_name = session.get('name', 'Cashier')
    conn, cursor = get_db()
    cursor.execute("SELECT * FROM employee_management WHERE password = %s AND position = 'manager'", (password,))
    manager = cursor.fetchone()
    
    if not manager:
        cursor.close()
        return jsonify({'success': False, 'message': 'Invalid Manager Password'}), 401
        
    manager_name = f"{manager['firstName']} {manager['lastName']}"

    cursor.execute("""
        SELECT o.*, m.menu_name, m.type, 
               t.transaction_code, t.guest_name,
               tb.table_name
        FROM order_items o
        JOIN main_menu_management m ON o.menu_id = m.menu_id
        JOIN transactions t ON o.transaction_id = t.id
        LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
        LEFT JOIN tables tb ON tt.table_id = tb.id
        WHERE o.id = %s
        LIMIT 1
    """, (item_id,))
    item_info = cursor.fetchone()

    if not item_info:
        cursor.close()
        return jsonify({'success': False, 'message': 'Item not found'}), 404

    if item_info['status'] in ['preparing', 'served']:
        cursor.execute("UPDATE main_menu_management SET availability = availability + %s WHERE menu_id = %s", (void_qty, item_info['menu_id']))

    if void_qty >= item_info['quantity']:
        cursor.execute("UPDATE order_items SET status = 'void', void_reason = %s WHERE id = %s", (reason, item_id))
    else:
        remaining_qty = item_info['quantity'] - void_qty
        remaining_total = float(remaining_qty * item_info['unit_price'])
        voided_total = float(void_qty * item_info['unit_price'])
        
        cursor.execute("UPDATE order_items SET quantity = %s, total_price = %s WHERE id = %s", (remaining_qty, remaining_total, item_id))
        cursor.execute("""
            INSERT INTO order_items
            (transaction_id, menu_id, unit_price, quantity, total_price, status, void_reason)
            VALUES (%s, %s, %s, %s, %s, 'void', %s)
        """, (item_info['transaction_id'], item_info['menu_id'], item_info['unit_price'], void_qty, voided_total, reason))

    cursor.execute("SELECT name, ip_address FROM kitchen_printer")
    printers = {row['name']: row['ip_address'] for row in cursor.fetchall()}
    conn.commit()
    cursor.close()

    item_type = item_info['type']
    station_printer_name = "BAR" if item_type == 'drinkable' or 'drink' in str(item_type).lower() or 'liquid' in str(item_type).lower() else "KITCHEN"

    if printers.get('CASHIER'):
        cashier_text = generate_void_receipt_text(item_info, void_qty, reason, cashier_name, manager_name, "CASHIER")
        print_to_escpos(cashier_text, printers.get('CASHIER'))

    if printers.get(station_printer_name):
        station_text = generate_void_receipt_text(item_info, void_qty, reason, cashier_name, manager_name, station_printer_name)
        print_to_escpos(station_text, printers.get(station_printer_name))
    
    return jsonify({'success': True, 'message': 'Item voided successfully'})

@app.route('/print_prebill/<int:tx_id>')
def print_prebill(tx_id):
    conn, cursor = get_db()
    cursor.execute('''
        SELECT t.*, GROUP_CONCAT(tb.table_name SEPARATOR ', ') as assigned_tables
        FROM transactions t
        LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
        LEFT JOIN tables tb ON tt.table_id = tb.id
        WHERE t.id = %s
        GROUP BY t.id
    ''', (tx_id,))
    txn = cursor.fetchone()
    
    cursor.execute('SELECT o.quantity, o.total_price, m.menu_name FROM order_items o JOIN main_menu_management m ON o.menu_id = m.menu_id WHERE o.transaction_id = %s AND o.status != "void"', (tx_id,))
    items = cursor.fetchall()
    
    cursor.execute("SELECT ip_address FROM kitchen_printer WHERE name = 'CASHIER'")
    printer = cursor.fetchone()
    cursor.close()
    
    subtotal = float(sum(i['total_price'] for i in items))
    sc = subtotal * get_service_charge_rate()
    
    receipt_text = generate_pre_receipt_text(txn, items, subtotal, sc, subtotal + sc)
    
    if printer and printer['ip_address']:
        print_to_escpos(receipt_text, printer['ip_address'])
    
    return jsonify({'success': True})

@app.route('/print_official_receipt/<int:tx_id>')
def print_official_receipt(tx_id):
    cashier_name = session.get('name', 'Cashier') 
    cashier_id = session.get('id', 1) 
    amount_given = float(request.args.get('given', 0.0))
    discount_val = float(request.args.get('discount', 0.0))
    
    conn, cursor = get_db()
    cursor.execute('''
        SELECT t.*, GROUP_CONCAT(tb.table_name SEPARATOR ', ') as assigned_tables
        FROM transactions t
        LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
        LEFT JOIN tables tb ON tt.table_id = tb.id
        WHERE t.id = %s
        GROUP BY t.id
    ''', (tx_id,))
    txn = cursor.fetchone()
    
    cursor.execute('SELECT o.quantity, o.unit_price, o.total_price, m.menu_name FROM order_items o JOIN main_menu_management m ON o.menu_id = m.menu_id WHERE o.transaction_id = %s AND o.status != "void"', (tx_id,))
    items = cursor.fetchall()
    
    cursor.execute('SELECT amount, payment_method, reference_number FROM payments WHERE transaction_id = %s ORDER BY id DESC LIMIT 1', (tx_id,))
    payment = cursor.fetchone()
    
    cursor.execute("SELECT ip_address FROM kitchen_printer WHERE name = 'CASHIER'")
    printer = cursor.fetchone()
    cashier_ip = printer['ip_address'] if printer else None
    
    if not payment:
        payment = {'payment_method': 'CASH', 'amount': 0, 'reference_number': 'N/A'}

    subtotal = float(sum(i['total_price'] for i in items))
    discount = round(discount_val, 2)
    discounted_subtotal = subtotal - discount
    sc = round(subtotal * get_service_charge_rate(), 2)
    grand_total = round(discounted_subtotal + sc, 2)
    vatable = round(discounted_subtotal / 1.12, 2)
    vat = round(discounted_subtotal - vatable, 2)
    tendered = round(amount_given if amount_given >= grand_total else grand_total, 2)
    change = round(tendered - grand_total, 2)
    
    payment['tendered'] = tendered
    payment['change'] = change
    payment['method'] = payment.get('payment_method', 'CASH')

    date_str = datetime.now().strftime("%Y%m%d")
    cursor.execute("SELECT COUNT(*) as count FROM receipts WHERE DATE(created_at) = CURDATE()")
    daily_receipt_count = cursor.fetchone()['count'] + 1
    or_number = f"OR-{date_str}-{daily_receipt_count:04d}"

    table_summary = txn.get('assigned_tables', 'No Table')
    payment_summary_text = f"{payment['method'].upper()} - Ref: {payment.get('reference_number', 'N/A')}"

    cursor.execute("""
        INSERT INTO receipts (transaction_id, receipt_number, guest_name, table_summary, total_amount, amount_paid, change_amount, payment_summary, printed_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (tx_id, or_number, txn.get('guest_name', 'Guest'), table_summary, grand_total, tendered, change, payment_summary_text, cashier_id))
    new_receipt_id = cursor.lastrowid

    for item in items:
        cursor.execute("INSERT INTO receipt_items (receipt_id, menu_name, quantity, unit_price, total_price) VALUES (%s, %s, %s, %s, %s)", (new_receipt_id, item['menu_name'], item['quantity'], float(item.get('unit_price', 0)), float(item['total_price'])))
    cursor.execute("INSERT INTO receipt_payments (receipt_id, payment_method, amount, reference_number) VALUES (%s, %s, %s, %s)", (new_receipt_id, payment['method'], tendered, payment.get('reference_number', 'N/A')))
    conn.commit()
    cursor.close()
    
    receipt_text = generate_official_receipt_text(txn, items, subtotal, discount, sc, vatable, vat, grand_total, payment, cashier_name)
    if cashier_ip:
        print_to_escpos(receipt_text, cashier_ip)
    
    return jsonify({'success': True, 'or_number': or_number})

@app.route('/print_free_receipt/<int:tx_id>')
def print_free_receipt(tx_id):
    manager_name = request.args.get('mgr', 'Manager')
    conn, cursor = get_db()
    cursor.execute('''
        SELECT t.*, GROUP_CONCAT(tb.table_name SEPARATOR ', ') as assigned_tables
        FROM transactions t
        LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
        LEFT JOIN tables tb ON tt.table_id = tb.id
        WHERE t.id = %s
        GROUP BY t.id
    ''', (tx_id,))
    txn = cursor.fetchone()
    
    cursor.execute('SELECT o.quantity, o.total_price, m.menu_name FROM order_items o JOIN main_menu_management m ON o.menu_id = m.menu_id WHERE o.transaction_id = %s AND o.status != "void"', (tx_id,))
    items = cursor.fetchall()
    
    cursor.execute("SELECT ip_address FROM kitchen_printer WHERE name = 'CASHIER'")
    printer = cursor.fetchone()
    cursor.close()
    
    subtotal = float(sum(i['total_price'] for i in items))
    sc = round(subtotal * get_service_charge_rate(), 2)
    grand_total = round(subtotal + sc, 2)
    vatable = round(subtotal / 1.12, 2)
    vat = round(subtotal - vatable, 2)
    
    receipt_text = generate_free_receipt_text(txn, items, subtotal, sc, vatable, vat, grand_total, manager_name)
    if printer and printer['ip_address']:
        print_to_escpos(receipt_text, printer['ip_address'])
    
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/transfer_table', methods=['POST'])
def transfer_table():
    data = request.json
    tx_id = data.get('transaction_id')
    new_table_id = data.get('new_table_id')

    if not tx_id or not new_table_id:
        return jsonify({'success': False, 'message': 'Missing data'}), 400

    try:
        conn, cursor = get_db()
        cursor.execute("SELECT table_id FROM transaction_tables WHERE transaction_id = %s LIMIT 1", (tx_id,))
        current_table_row = cursor.fetchone()
        old_table_id = current_table_row['table_id'] if current_table_row else None
        
        if not old_table_id or old_table_id == new_table_id:
            return jsonify({'success': False, 'message': 'Invalid table transfer request.'}), 400

        cursor.execute("SELECT status FROM tables WHERE id = %s", (new_table_id,))
        new_table = cursor.fetchone()
        if not new_table or new_table['status'] != 'vacant':
            return jsonify({'success': False, 'message': 'Target table is not vacant.'}), 400

        cursor.execute("UPDATE transaction_tables SET table_id = %s WHERE transaction_id = %s", (new_table_id, tx_id))
        cursor.execute("UPDATE tables SET status = 'vacant' WHERE id = %s", (old_table_id,))
        cursor.execute("UPDATE tables SET status = 'occupied' WHERE id = %s", (new_table_id,))
        cursor.execute("INSERT INTO table_transfers (transaction_id, from_table_id, to_table_id, type) VALUES (%s, %s, %s, 'single')", (tx_id, old_table_id, new_table_id))
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Table transferred successfully!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Database error'}), 500

@app.route('/api/add_multiple_table', methods=['POST'])
def add_multiple_table():
    data = request.json
    tx_id = data.get('transaction_id')
    new_table_id = data.get('new_table_id')
    if not tx_id or not new_table_id:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
    try:
        conn, cursor = get_db()
        cursor.execute("SELECT status FROM tables WHERE id = %s", (new_table_id,))
        new_table = cursor.fetchone()
        if not new_table or new_table['status'] != 'vacant':
            return jsonify({'success': False, 'message': 'Target table is not vacant.'}), 400
        cursor.execute("INSERT INTO transaction_tables (transaction_id, table_id) VALUES (%s, %s)", (tx_id, new_table_id))
        cursor.execute("UPDATE tables SET status = 'occupied' WHERE id = %s", (new_table_id,))
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Table successfully added to transaction!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Database error'}), 500

@app.route('/api/merge_transactions', methods=['POST'])
def merge_transactions():
    data = request.json
    source_tx_id = data.get('source_transaction_id')
    target_tx_id = data.get('target_transaction_id')

    if not source_tx_id or not target_tx_id or source_tx_id == target_tx_id:
        return jsonify({'success': False, 'message': 'Invalid transaction IDs for merge.'}), 400

    try:
        conn, cursor = get_db()
        
        cursor.execute("SELECT guest_count, guest_name FROM transactions WHERE id = %s", (source_tx_id,))
        source_row = cursor.fetchone()
        source_guest_count = source_row['guest_count'] if source_row else 0
        source_guest_name = source_row['guest_name'] if source_row else 'Guest'
        
        cursor.execute("UPDATE transactions SET guest_count = guest_count + %s WHERE id = %s", (source_guest_count, target_tx_id))
        
        cursor.execute("SELECT id FROM transaction_guests WHERE transaction_id = %s AND guest_name = %s", (source_tx_id, source_guest_name))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO transaction_guests (transaction_id, guest_name, is_primary) VALUES (%s, %s, FALSE)", (source_tx_id, source_guest_name))

        cursor.execute("UPDATE order_items SET transaction_id = %s WHERE transaction_id = %s", 
                       (target_tx_id, source_tx_id))
        
        cursor.execute("UPDATE IGNORE transaction_tables SET transaction_id = %s WHERE transaction_id = %s", 
                       (target_tx_id, source_tx_id))
        
        cursor.execute("UPDATE transaction_guests SET transaction_id = %s, is_primary = FALSE WHERE transaction_id = %s", 
                       (target_tx_id, source_tx_id))
        
        cursor.execute("UPDATE transactions SET status = 'merged' WHERE id = %s", (source_tx_id,))
        
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Tables successfully merged!'})
    except Exception as e:
        conn.rollback()
        print(f"Merge error: {e}")
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

@app.route('/api/separate_check', methods=['POST'])
def separate_check():
    data = request.json
    original_tx_id = data.get('original_transaction_id')
    items_to_move = data.get('items', []) 
    leaver_name = data.get('guest_name', 'Early Leaver')

    if not original_tx_id or not items_to_move:
        return jsonify({'success': False, 'message': 'Missing data for separate check.'}), 400

    try:
        conn, cursor = get_db()
        
        date_str = datetime.now().strftime("%y%m%d")
        cursor.execute("SELECT COUNT(*) as count FROM transactions WHERE DATE(created_at) = CURDATE()")
        daily_count = cursor.fetchone()['count'] + 1
        new_txn_code = f"SPL-{date_str}-{daily_count:03d}" 
        
        cursor.execute("""
            INSERT INTO transactions (transaction_code, guest_name, guest_count, status) 
            VALUES (%s, %s, 1, 'open')
        """, (new_txn_code, leaver_name))
        new_tx_id = cursor.lastrowid
        
        for item_data in items_to_move:
            item_id = item_data['item_id']
            qty_to_move = int(item_data['qty'])
            
            if qty_to_move <= 0:
                continue
                
            cursor.execute("SELECT * FROM order_items WHERE id = %s AND transaction_id = %s", (item_id, original_tx_id))
            current_item = cursor.fetchone()
            
            if not current_item:
                continue
                
            if qty_to_move >= current_item['quantity']:
                cursor.execute("UPDATE order_items SET transaction_id = %s WHERE id = %s", (new_tx_id, item_id))
            else:
                remaining_qty = current_item['quantity'] - qty_to_move
                unit_price = float(current_item['unit_price'])
                
                cursor.execute("""
                    UPDATE order_items 
                    SET quantity = %s, total_price = %s 
                    WHERE id = %s
                """, (remaining_qty, remaining_qty * unit_price, item_id))
                
                cursor.execute("""
                    INSERT INTO order_items (transaction_id, menu_id, quantity, unit_price, total_price, status, note, waiter_name)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (new_tx_id, current_item['menu_id'], qty_to_move, unit_price, qty_to_move * unit_price, current_item['status'], current_item['note'], current_item['waiter_name']))
        
        cursor.execute("""
            UPDATE transactions 
            SET guest_count = GREATEST(guest_count - 1, 1) 
            WHERE id = %s
        """, (original_tx_id,))

        original_guest_name = leaver_name.replace(" (Early Leaver)", "").strip()
        cursor.execute("""
            DELETE FROM transaction_guests 
            WHERE transaction_id = %s AND guest_name = %s 
            LIMIT 1
        """, (original_tx_id, original_guest_name))
        
        conn.commit()
        cursor.close()
        
        return jsonify({
            'success': True, 
            'new_transaction_id': new_tx_id,
            'message': 'Items separated successfully. Ready for payment.'
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Separate check error: {e}")
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

@app.route('/api/tables', methods=['GET'])
def get_tables():
    try:
        conn, cursor = get_db()
        cursor.execute("SELECT id, table_name, capacity, status FROM tables")
        tables = cursor.fetchall()
        cursor.close()
        
        table_data = {}
        for t in tables:
            if t['id'] <= 8:
                base_ref, type_name = 'stool', 'Barstool'
            elif t['id'] in [9, 10, 11, 20, 21, 22]:
                base_ref, type_name = 'barrel', 'Barrel'
            else:
                base_ref, type_name = 'bagbeans', 'Bagbeans'
                
            table_data[t['id']] = {
                'id': t['id'],
                'name': t['table_name'],
                'type': type_name,
                'capacity': t['capacity'],
                'status': t['status'],
                'baseRef': base_ref
            }
        return jsonify({'success': True, 'tables': table_data})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Database error'}), 500

@app.route('/api/table_details/<int:table_id>', methods=['GET'])
def get_table_details(table_id):
    try:
        conn, cursor = get_db()
        
        cursor.execute("""
            SELECT t.id as transaction_id, t.guest_name, t.contact_number, t.guest_count 
            FROM transactions t
            JOIN transaction_tables tt ON t.id = tt.transaction_id
            WHERE tt.table_id = %s AND t.status = 'open'
            LIMIT 1
        """, (table_id,))
        txn = cursor.fetchone()
        
        if txn:
            cursor.execute("""
                SELECT SUM(tbl.capacity) AS total_capacity 
                FROM tables tbl
                JOIN transaction_tables tt ON tbl.id = tt.table_id
                WHERE tt.transaction_id = %s
            """, (txn['transaction_id'],))
            
            capacity_result = cursor.fetchone()
            
            txn['total_capacity'] = capacity_result['total_capacity'] if capacity_result and capacity_result['total_capacity'] else 4

            cursor.execute("""
                SELECT o.id as item_id, m.menu_name, o.quantity, o.status, o.note
                FROM order_items o
                JOIN main_menu_management m ON o.menu_id = m.menu_id
                WHERE o.transaction_id = %s AND o.status != 'void'
            """, (txn['transaction_id'],))
            txn['orders'] = cursor.fetchall() 
            
            cursor.close()
            return jsonify({'success': True, 'data': txn})
            
        cursor.close()
        return jsonify({'success': False, 'message': 'No active transaction found'})
        
    except Exception as e:
        print(f"Error in get_table_details: {e}") 
        return jsonify({'success': False, 'message': 'Database error'}), 500
    
@app.route('/api/add_guest', methods=['POST'])
def add_guest():
    data = request.json
    tx_id = data.get('transaction_id')
    guest_names = data.get('guest_names', [])
    
    if not tx_id or not guest_names:
        return jsonify({'success': False, 'message': 'Missing transaction ID or guest names'}), 400
        
    try:
        conn, cursor = get_db()
        
        for guest_name in guest_names:
            cursor.execute(
                "INSERT INTO transaction_guests (transaction_id, guest_name, is_primary) VALUES (%s, %s, FALSE)", 
                (tx_id, guest_name)
            )
        
        number_of_new_guests = len(guest_names)
        cursor.execute(
            "UPDATE transactions SET guest_count = guest_count + %s WHERE id = %s", 
            (number_of_new_guests, tx_id)
        )
        
        conn.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': f'{number_of_new_guests} guest(s) added successfully!'})
        
    except Exception as e:
        conn.rollback()
        print(f"Error adding multiple guests: {e}")
        return jsonify({'success': False, 'message': 'Database error'}), 500

@app.route('/api/update_item_status', methods=['POST'])
def update_item_status():
    data = request.json
    item_id = data.get('item_id')
    new_status = data.get('status') 
    if not item_id or not new_status:
        return jsonify({'success': False, 'message': 'Missing data'}), 400
    try:
        conn, cursor = get_db()
        
        cursor.execute("SELECT status, quantity, menu_id FROM order_items WHERE id = %s", (item_id,))
        current_item = cursor.fetchone()
        
        if current_item and current_item['status'] == 'pending' and new_status == 'preparing':
            cursor.execute("UPDATE main_menu_management SET availability = availability - %s WHERE menu_id = %s", (current_item['quantity'], current_item['menu_id']))
        
        cursor.execute("UPDATE order_items SET status = %s WHERE id = %s", (new_status, item_id))
        
        cursor.execute("""
            SELECT o.quantity, o.status, m.menu_name, m.type, t.transaction_code, t.guest_name, tb.table_name
            FROM order_items o
            JOIN main_menu_management m ON o.menu_id = m.menu_id
            JOIN transactions t ON o.transaction_id = t.id
            LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
            LEFT JOIN tables tb ON tt.table_id = tb.id
            WHERE o.id = %s LIMIT 1
        """, (item_id,))
        item_info = cursor.fetchone()
        cursor.execute("SELECT name, ip_address FROM kitchen_printer")
        printers = {row['name']: row['ip_address'] for row in cursor.fetchall()}
        conn.commit()
        cursor.close()
        
        if item_info and new_status == 'preparing':
            txn_data = {'transaction_code': item_info['transaction_code'], 'guest_name': item_info['guest_name'], 'assigned_tables': item_info['table_name'] if item_info['table_name'] else "No Table"}
            receipt_item = {'menu_name': item_info['menu_name'], 'quantity': item_info['quantity'], 'status': item_info['status'], 'type': item_info['type']}
            item_type = item_info['type']
            printer_name = "BAR" if item_type == 'drinkable' or 'drink' in str(item_type).lower() or 'liquid' in str(item_type).lower() else "KITCHEN"
            printer_ip = printers.get(printer_name)
            if printer_ip:
                from specific_receipt import generate_specific_receipt_text
                receipt_text = generate_specific_receipt_text(txn_data, [receipt_item], printer_name)
                print_to_escpos(receipt_text, printer_ip)
                message = f'Status updated! Ticket printed at {printer_name}.'
            else:
                message = f'Status updated, but {printer_name} printer IP is missing.'
        else:
            message = 'Status updated successfully.'
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Database error'}), 500

@app.route('/api/tables/<int:table_id>', methods=['PUT'])
def update_table_status(table_id):
    data = request.get_json()
    new_status = data.get('status')
    if new_status not in ['vacant', 'occupied']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    try:
        conn, cursor = get_db()
        cursor.execute("UPDATE tables SET status = %s WHERE id = %s", (new_status, table_id))
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Table status updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Database error'}), 500
    
@app.route('/api/menu', methods=['GET'])
def get_menu():
    try:
        conn, cursor = get_db()
        cursor.execute("SELECT * FROM main_menu_management WHERE availability > 0")
        menu = cursor.fetchall()
        for item in menu:
            item['unit_price'] = float(item['unit_price'])
        cursor.close()
        return jsonify({'success': True, 'menu': menu})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Database error'}), 500
    
@app.route('/api/occupy_table_only', methods=['POST'])
def occupy_table_only():
    data = request.json
    table_id = data.get('table_id')
    
    primary_name = data.get('primary_name')
    if not primary_name:
        primary_name = 'Guest'
        
    contact = data.get('contact', '')
    total_guests = data.get('total_guests', 1)
    additional_guests = data.get('additional_guests', [])
    
    if not table_id:
        return jsonify({'success': False, 'message': 'Missing table information.'}), 400

    try:
        conn, cursor = get_db()
        
        date_str = datetime.now().strftime("%Y%m%d")
        cursor.execute("SELECT COUNT(*) as count FROM transactions WHERE DATE(created_at) = CURDATE()")
        daily_count = cursor.fetchone()['count'] + 1
        txn_code = f"TRX-{date_str}-{daily_count:03d}"
        
        cursor.execute("""
            INSERT INTO transactions (transaction_code, guest_name, contact_number, guest_count, status) 
            VALUES (%s, %s, %s, %s, 'open')
        """, (txn_code, primary_name, contact, total_guests))
        tx_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO transaction_tables (transaction_id, table_id) VALUES (%s, %s)", (tx_id, table_id))
        cursor.execute("UPDATE tables SET status = 'occupied' WHERE id = %s", (table_id,))
        cursor.execute("INSERT INTO transaction_guests (transaction_id, guest_name, is_primary) VALUES (%s, %s, TRUE)", (tx_id, primary_name))
        
        for guest in additional_guests:
            cursor.execute("INSERT INTO transaction_guests (transaction_id, guest_name, is_primary) VALUES (%s, %s, FALSE)", (tx_id, guest))
            
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Table successfully occupied without initial orders.'})
    except Exception as e:
        conn.rollback()
        print(f"Error in occupy_table_only: {e}")
        return jsonify({'success': False, 'message': 'Database error occurred.'}), 500

@app.route('/api/cancel_transaction', methods=['POST'])
def cancel_transaction():
    data = request.json
    tx_id = data.get('transaction_id')
    
    if not tx_id:
        return jsonify({'success': False, 'message': 'Missing transaction ID.'}), 400

    try:
        conn, cursor = get_db()
        
        cursor.execute("SELECT COUNT(*) FROM order_items WHERE transaction_id = %s AND status != 'cancelled'", (tx_id,))
        active_orders = cursor.fetchone()[0]
        
        if active_orders > 0:
            return jsonify({'success': False, 'message': 'Cannot cancel. This table already has active orders.'}), 400

        cursor.execute("UPDATE transactions SET status = 'cancelled' WHERE id = %s", (tx_id,))
        
        cursor.execute("""
            UPDATE tables 
            SET status = 'vacant' 
            WHERE id IN (
                SELECT table_id FROM transaction_tables WHERE transaction_id = %s
            )
        """, (tx_id,))
        
        conn.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': 'Transaction successfully cancelled and table vacated.'})
        
    except Exception as e:
        conn.rollback()
        print(f"Error cancelling transaction: {e}")
        return jsonify({'success': False, 'message': 'Database error occurred.'}), 500

@app.route('/api/place_order', methods=['POST'])
def place_order():
    data = request.json
    table_id = data.get('table_id')
    primary_name = data.get('primary_name')
    contact = data.get('contact')
    email = data.get('email')
    guest_count = data.get('total_guests', 1)
    additional_guests = data.get('additional_guests', [])
    cart = data.get('cart', [])
    waiter_name = data.get('waiter_name', 'Unknown')
    tx_id = data.get('transaction_id') 

    if not table_id or not cart:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    try:
        date_str = datetime.now().strftime("%Y%m%d")
        conn, cursor = get_db()
        cursor.execute("SELECT table_name FROM tables WHERE id = %s", (table_id,))
        t_row = cursor.fetchone()
        table_name = t_row['table_name'] if t_row else "No Table"

        if tx_id:
            txn_id = tx_id
            cursor.execute("SELECT transaction_code, guest_name FROM transactions WHERE id = %s", (txn_id,))
            txn_row = cursor.fetchone()
            if not txn_row:
                return jsonify({'success': False, 'message': 'Transaction not found'}), 404
            txn_code = txn_row['transaction_code']
            primary_name = txn_row['guest_name'] 
        else:
            if not primary_name:
                primary_name = 'Guest'
                
            cursor.execute("SELECT COUNT(*) as count FROM transactions WHERE DATE(created_at) = CURDATE()")
            daily_count = cursor.fetchone()['count'] + 1
            txn_code = f"TRX-{date_str}-{daily_count:03d}"
            cursor.execute("INSERT INTO transactions (transaction_code, guest_name, contact_number, guest_email, guest_count, status) VALUES (%s, %s, %s, %s, %s, 'open')", (txn_code, primary_name, contact, email, guest_count))
            txn_id = cursor.lastrowid
            for g_name in additional_guests:
                cursor.execute("INSERT INTO transaction_guests (transaction_id, guest_name, is_primary) VALUES (%s, %s, FALSE)", (txn_id, g_name))
            cursor.execute("INSERT INTO transaction_tables (transaction_id, table_id) VALUES (%s, %s)", (txn_id, table_id))
            cursor.execute("UPDATE tables SET status = 'occupied' WHERE id = %s", (table_id,))

        bar_items = []
        kitchen_items = []

        for item in cart:
            total_price = item['qty'] * item['unit_price']
            item_status = item.get('status', 'pending') 
            item_type = item.get('type', 'solid')
            item_note = item.get('note', '')
            
            cursor.execute("INSERT INTO order_items (transaction_id, menu_id, quantity, unit_price, total_price, status, note, waiter_name) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (txn_id, item['menu_id'], item['qty'], item['unit_price'], total_price, item_status, item_note, waiter_name))
            
            if item_status == 'preparing':
                cursor.execute("UPDATE main_menu_management SET availability = availability - %s WHERE menu_id = %s", (item['qty'], item['menu_id']))

            receipt_item = {'menu_name': item['name'], 'quantity': item['qty'], 'status': item_status, 'type': item_type, 'note': item_note}
            if item_type == 'drinkable' or 'drink' in item_type.lower() or 'liquid' in item_type.lower():
                bar_items.append(receipt_item)
            else:
                kitchen_items.append(receipt_item)

        cursor.execute("SELECT name, ip_address FROM kitchen_printer")
        printers = {row['name']: row['ip_address'] for row in cursor.fetchall()}
        conn.commit()
        cursor.close()
        
        txn_data = {'transaction_code': txn_code, 'guest_name': primary_name, 'assigned_tables': table_name}
        if bar_items and printers.get('BAR'):
            bar_text = generate_specific_receipt_text(txn_data, bar_items, "BAR")
            print_to_escpos(bar_text, printers.get('BAR'))
        if kitchen_items and printers.get('KITCHEN'):
            kitchen_text = generate_specific_receipt_text(txn_data, kitchen_items, "KITCHEN")
            print_to_escpos(kitchen_text, printers.get('KITCHEN'))
        return jsonify({'success': True, 'message': 'Order successfully placed!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Database error while placing order.'}), 500

@app.route('/process_payment', methods=['POST'])
def process_payment():
    data = request.get_json()
    tx_id = data.get('transaction_id')
    method = data.get('method', 'cash')
    amount = data.get('amount_paid', 0)
    ref_num = data.get('reference_number', None)
    
    cashier_id = session.get('id')
    
    if not tx_id:
        return jsonify({'success': False, 'message': 'Missing Transaction ID'}), 400
    
    try:
        conn, cursor = get_db()
        
        cursor.execute("SELECT id FROM cash_drawer WHERE employee_id = %s AND status = 'open' LIMIT 1", (cashier_id,))
        active_shift = cursor.fetchone()
        shift_id = active_shift['id'] if active_shift else None
        
        cursor.execute("UPDATE transactions SET status = 'paid' WHERE id = %s", (tx_id,))
        
        cursor.execute("""
            INSERT INTO payments (transaction_id, shift_id, amount, payment_method, reference_number) 
            VALUES (%s, %s, %s, %s, %s)
        """, (tx_id, shift_id, amount, method, ref_num))
        
        voucher_code = data.get('voucher_code')
        if voucher_code:
            cursor.execute("UPDATE vouchers SET current_uses = current_uses + 1 WHERE voucher_code = %s", (voucher_code,))
            cursor.execute("UPDATE vouchers SET status = 'used' WHERE voucher_code = %s AND max_uses > 0 AND current_uses >= max_uses", (voucher_code,))
        
        cursor.execute("SELECT table_id FROM transaction_tables WHERE transaction_id = %s", (tx_id,))
        tables_to_free = cursor.fetchall()
        if tables_to_free:
            for row in tables_to_free:
                cursor.execute("UPDATE tables SET status = 'vacant' WHERE id = %s", (row['table_id'],))
        
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Payment successful and tables are now vacant!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/process_split_payments', methods=['POST'])
def process_split_payments():
    data = request.json
    tx_id = data.get('transaction_id')
    split_type = data.get('split_type')
    splits = data.get('splits', [])
    cashier_id = session.get('id')

    try:
        conn, cursor = get_db()
        cursor.execute("SELECT id FROM cash_drawer WHERE employee_id = %s AND status = 'open' LIMIT 1", (cashier_id,))
        active_shift = cursor.fetchone()
        shift_id = active_shift['id'] if active_shift else None
        
        cursor.execute("UPDATE transactions SET status = 'paid' WHERE id = %s", (tx_id,))
        split_ids = []

        for split in splits:
            split_name = split.get('split_name', 'Split')
            amount = float(split.get('amount', 0))
            method = split.get('method', 'cash')
            ref_num = split.get('reference_number', '')
            discount = float(split.get('discount', 0))
            items = split.get('items', []) 

            cursor.execute("INSERT INTO bill_splits (transaction_id, split_name, split_type, amount) VALUES (%s, %s, %s, %s)", (tx_id, split_name, split_type, amount))
            split_id = cursor.lastrowid
            split_ids.append(split_id)
            
            actual_paid = amount - discount
            cursor.execute("""
                INSERT INTO payments (transaction_id, split_id, shift_id, amount, payment_method, reference_number) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (tx_id, split_id, shift_id, actual_paid, method, ref_num))

            if split_type == 'items' and items:
                for item_obj in items:
                    if isinstance(item_obj, dict):
                        item_id = item_obj.get('item_id')
                        qty = item_obj.get('quantity', 1)
                    else:
                        item_id = item_obj
                        qty = 1
                    cursor.execute("INSERT INTO bill_split_items (split_id, order_item_id, quantity) VALUES (%s, %s, %s)", (split_id, item_id, qty))

        voucher_code = data.get('voucher_code')
        if voucher_code:
            cursor.execute("UPDATE vouchers SET current_uses = current_uses + 1 WHERE voucher_code = %s", (voucher_code,))
            cursor.execute("UPDATE vouchers SET status = 'used' WHERE voucher_code = %s AND max_uses > 0 AND current_uses >= max_uses", (voucher_code,))

        cursor.execute('''
            SELECT o.quantity, o.unit_price, o.total_price, m.menu_name 
            FROM order_items o 
            JOIN main_menu_management m ON o.menu_id = m.menu_id 
            WHERE o.transaction_id = %s AND o.status != "void"
        ''', (tx_id,))
        order_items = cursor.fetchall()
        
        subtotal = float(sum(i['total_price'] for i in order_items))
        total_discount = sum(float(s.get('discount', 0)) for s in splits)
        discounted_subtotal = subtotal - total_discount
        sc = round(subtotal * get_service_charge_rate(), 2)
        grand_total = round(discounted_subtotal + sc, 2)
        
        total_tendered = sum(
            float(s.get('amount_given', 0)) if s.get('method', 'cash').lower() == 'cash' 
            else (float(s.get('amount', 0)) - float(s.get('discount', 0))) 
            for s in splits
        )
        total_change = round(total_tendered - grand_total, 2)
        
        date_str = datetime.now().strftime("%Y%m%d")
        cursor.execute("SELECT COUNT(*) as count FROM receipts WHERE DATE(created_at) = CURDATE()")
        daily_receipt_count = cursor.fetchone()['count'] + 1
        or_number = f"OR-{date_str}-{daily_receipt_count:04d}"
        
        cursor.execute("SELECT guest_name FROM transactions WHERE id = %s", (tx_id,))
        txn_row = cursor.fetchone()
        guest_name = txn_row['guest_name'] if txn_row else 'Guest'
        
        cursor.execute("SELECT GROUP_CONCAT(tb.table_name SEPARATOR ', ') as assigned_tables FROM transaction_tables tt JOIN tables tb ON tt.table_id = tb.id WHERE tt.transaction_id = %s", (tx_id,))
        ts_row = cursor.fetchone()
        table_summary = ts_row['assigned_tables'] if ts_row and ts_row['assigned_tables'] else 'No Table'
        
        payment_summary_text = f"SPLIT BILL ({len(splits)} splits)"
        
        cursor.execute("""
            INSERT INTO receipts (transaction_id, receipt_number, guest_name, table_summary, total_amount, amount_paid, change_amount, payment_summary, printed_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (tx_id, or_number, guest_name, table_summary, grand_total, total_tendered, total_change, payment_summary_text, cashier_id))
        new_receipt_id = cursor.lastrowid
        
        for item in order_items:
            cursor.execute("INSERT INTO receipt_items (receipt_id, menu_name, quantity, unit_price, total_price) VALUES (%s, %s, %s, %s, %s)", 
                           (new_receipt_id, item['menu_name'], item['quantity'], float(item.get('unit_price', 0)), float(item['total_price'])))
            
        for split in splits:
            method = split.get('method', 'cash')
            amt = float(split.get('amount', 0)) - float(split.get('discount', 0))
            ref = split.get('reference_number', 'N/A')
            cursor.execute("INSERT INTO receipt_payments (receipt_id, payment_method, amount, reference_number) VALUES (%s, %s, %s, %s)", 
                           (new_receipt_id, method, amt, ref))

        cursor.execute("SELECT table_id FROM transaction_tables WHERE transaction_id = %s", (tx_id,))
        tables_to_free = cursor.fetchall()
        if tables_to_free:
            for row in tables_to_free:
                cursor.execute("UPDATE tables SET status = 'vacant' WHERE id = %s", (row['table_id'],))
        
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'split_ids': split_ids})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/print_split_receipt/<int:split_id>')
def print_split_receipt(split_id):
    cashier_name = session.get('name', 'Cashier') 
    amount_given = float(request.args.get('given', 0.0))
    discount_val = float(request.args.get('discount', 0.0))

    conn, cursor = get_db()
    cursor.execute("SELECT * FROM bill_splits WHERE id = %s", (split_id,))
    split_info = cursor.fetchone()
    if not split_info:
        return jsonify({'success': False, 'message': 'Split not found'})
        
    tx_id = split_info['transaction_id']

    cursor.execute('''
        SELECT t.*, GROUP_CONCAT(tb.table_name SEPARATOR ', ') as assigned_tables
        FROM transactions t
        LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
        LEFT JOIN tables tb ON tt.table_id = tb.id
        WHERE t.id = %s
        GROUP BY t.id
    ''', (tx_id,))
    txn = cursor.fetchone()

    cursor.execute('SELECT amount, payment_method, reference_number FROM payments WHERE split_id = %s ORDER BY id DESC LIMIT 1', (split_id,))
    payment = cursor.fetchone()

    cursor.execute("SELECT split_name, amount FROM bill_splits WHERE transaction_id = %s", (tx_id,))
    all_splits_for_txn = cursor.fetchall()

    cursor.execute('''
        SELECT o.quantity, o.total_price, m.menu_name 
        FROM order_items o 
        JOIN main_menu_management m ON o.menu_id = m.menu_id 
        WHERE o.transaction_id = %s AND o.status != 'void'
    ''', (tx_id,))
    items = cursor.fetchall()
    
    split_items = []
    if split_info['split_type'] == 'items':
        cursor.execute('''
            SELECT bsi.quantity, (bsi.quantity * o.unit_price) as total_price, m.menu_name 
            FROM bill_split_items bsi
            JOIN order_items o ON bsi.order_item_id = o.id
            JOIN main_menu_management m ON o.menu_id = m.menu_id
            WHERE bsi.split_id = %s
        ''', (split_id,))
        split_items = cursor.fetchall()
    
    subtotal = float(sum(i['total_price'] for i in items))
    cursor.execute("SELECT ip_address FROM kitchen_printer WHERE name = 'CASHIER'")
    printer = cursor.fetchone()
    cashier_ip = printer['ip_address'] if printer else None
    cursor.close()

    if not payment:
        payment = {'payment_method': 'CASH', 'amount': 0, 'reference_number': 'N/A'}

    sc = round(subtotal * get_service_charge_rate(), 2)
    grand_total = round(subtotal + sc, 2)
    vatable = round(subtotal / 1.12, 2)
    vat = round(subtotal - vatable, 2)

    split_gross = float(split_info['amount'])
    net_split = round(split_gross - discount_val, 2)
    tendered = round(amount_given if amount_given >= net_split else net_split, 2)
    change = round(tendered - net_split, 2)

    payment['tendered'] = tendered
    payment['change'] = change
    payment['method'] = payment.get('payment_method', 'CASH')

    formatted_split_name = split_info['split_name']
    if discount_val > 0:
        formatted_split_name += f" (Disc: -{discount_val:.2f})"

    split_data_dict = {
        'split_type': split_info['split_type'],
        'split_name': formatted_split_name,
        'amount': net_split,
        'split_items': split_items 
    }

    receipt_text = generate_official_receipt_text(
        txn, items, subtotal, 0.0, sc, vatable, vat, grand_total, payment, cashier_name, 
        split_data=split_data_dict, all_splits=all_splits_for_txn
    )

    if cashier_ip:
        print_to_escpos(receipt_text, cashier_ip)

    return jsonify({'success': True})

@app.route('/api/manager/settings', methods=['GET'])
def get_all_settings():
    if session.get('role') != 'manager':
        return jsonify({'success': False}), 403
    try:
        conn, cursor = get_db()
        cursor.execute("SELECT * FROM system_settings")
        settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
        cursor.close()
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manager/settings/save', methods=['POST'])
def save_settings():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json
    try:
        conn, cursor = get_db()
        for key, value in data.items():
            cursor.execute("""
                INSERT INTO system_settings (setting_key, setting_value) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
            """, (key, value))
        
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Settings saved successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manager/dashboard_stats')
def get_dashboard_stats():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    date_cond = "DATE(created_at) = CURDATE()"
    params = []
    
    if from_date and to_date:
        date_cond = "DATE(created_at) BETWEEN %s AND %s"
        params = [from_date, to_date]
    elif from_date:
        date_cond = "DATE(created_at) >= %s"
        params = [from_date]
    elif to_date:
        date_cond = "DATE(created_at) <= %s"
        params = [to_date]
        
    conn, cursor = get_db()
    
    cursor.execute(f"SELECT SUM(total_amount) as total FROM receipts WHERE {date_cond}", tuple(params))
    revenue_row = cursor.fetchone()
    revenue = float(revenue_row['total'] or 0)
    
    cursor.execute(f"""
        SELECT SUM(o.total_price) as gross
        FROM order_items o
        JOIN transactions t ON o.transaction_id = t.id
        WHERE t.status = 'paid' AND o.status != 'void' AND {date_cond.replace('created_at', 't.created_at')}
    """, tuple(params))
    gross_row = cursor.fetchone()
    gross_sales = float(gross_row['gross'] or 0)
    expected_total = gross_sales + (gross_sales * get_service_charge_rate())
    
    total_discount = round(expected_total - revenue, 2)
    if total_discount < 0: total_discount = 0.0

    net_sales = round(revenue / 1.12, 2)

    cursor.execute(f"""
        SELECT payment_method, COUNT(*) as count, SUM(amount) as total_amount
        FROM payments 
        WHERE {date_cond}
        GROUP BY payment_method
    """, tuple(params))
    payment_methods = cursor.fetchall()
    
    top_pm_count = "N/A"
    top_pm_sales = "N/A"
    breakdown = {'cash': 0.0, 'qrph': 0.0, 'card': 0.0}
    
    if payment_methods:
        sorted_by_count = sorted(payment_methods, key=lambda x: x['count'], reverse=True)
        pm_c = str(sorted_by_count[0]['payment_method']).upper()
        top_pm_count = 'QRPh' if pm_c == 'QRPH' else pm_c.capitalize()

        sorted_by_sales = sorted(payment_methods, key=lambda x: float(x['total_amount'] or 0), reverse=True)
        pm_s = str(sorted_by_sales[0]['payment_method']).upper()
        top_pm_sales = 'QRPh' if pm_s == 'QRPH' else pm_s.capitalize()
        
        for pm in payment_methods:
            method_name = str(pm['payment_method']).lower()
            if method_name in breakdown:
                breakdown[method_name] = float(pm['total_amount'] or 0)
                
    cursor.execute(f"SELECT SUM(total_price) as void_amount, SUM(quantity) as void_qty FROM order_items WHERE status = 'void' AND {date_cond}", tuple(params))
    void_data = cursor.fetchone()
    void_amount = float(void_data['void_amount'] or 0)
    void_qty = int(void_data['void_qty'] or 0)
    
    cursor.execute(f"SELECT COUNT(*) as count FROM transactions WHERE status = 'cancelled' AND {date_cond}", tuple(params))
    cancelled_count = cursor.fetchone()['count'] or 0
    
    cursor.execute("SELECT SUM(guest_count) as count FROM transactions WHERE status = 'open'")
    active_guests = cursor.fetchone()['count'] or 0
    
    cursor.execute("SELECT COUNT(*) as count FROM tables WHERE status = 'occupied'")
    occupied_tables = cursor.fetchone()['count'] or 0
    
    cursor.execute(f"SELECT COUNT(*) as count FROM receipts WHERE {date_cond}", tuple(params))
    total_txns = cursor.fetchone()['count'] or 0
    
    cursor.execute(f"SELECT SUM(guest_count) as count FROM transactions WHERE status NOT IN ('cancelled', 'merged') AND {date_cond}", tuple(params))
    total_guests_today = cursor.fetchone()['count'] or 0
    
    cursor.execute(f"""
        SELECT DATE(created_at) as date, SUM(total_amount) as total 
        FROM receipts 
        WHERE {date_cond}
        GROUP BY DATE(created_at) ORDER BY date ASC
    """, tuple(params))
    trend = cursor.fetchall()

    cursor.execute(f"""
        SELECT HOUR(created_at) as hour, SUM(total_amount) as sales 
        FROM receipts 
        WHERE {date_cond}
        GROUP BY HOUR(created_at) ORDER BY hour ASC
    """, tuple(params))
    hourly_sales = cursor.fetchall()
    
    cursor.execute(f"""
        SELECT m.category, SUM(o.total_price) as sales 
        FROM order_items o 
        JOIN main_menu_management m ON o.menu_id = m.menu_id 
        WHERE o.status != 'void' AND {date_cond.replace('created_at', 'o.created_at')}
        GROUP BY m.category ORDER BY sales DESC
    """, tuple(params))
    category_sales = cursor.fetchall()
    
    cursor.execute(f"""
        SELECT ri.menu_name, SUM(ri.quantity) as total_sold 
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE {date_cond.replace('created_at', 'r.created_at')}
        GROUP BY ri.menu_name ORDER BY total_sold DESC LIMIT 5
    """, tuple(params))
    top_items = cursor.fetchall()
    
    cursor.execute(f"""
        SELECT m.type, SUM(o.total_price) as sales 
        FROM order_items o 
        JOIN main_menu_management m ON o.menu_id = m.menu_id 
        WHERE o.status != 'void' AND {date_cond.replace('created_at', 'o.created_at')}
        GROUP BY m.type
    """, tuple(params))
    type_performance = cursor.fetchall()
    
    cursor.execute(f"""
        SELECT waiter_name, SUM(quantity) as items_served, SUM(total_price) as total_sales
        FROM order_items 
        WHERE status != 'void' AND waiter_name != 'Unknown' AND {date_cond}
        GROUP BY waiter_name 
        ORDER BY total_sales DESC LIMIT 5
    """, tuple(params))
    top_waiters = cursor.fetchall()

    cursor.close()
    return jsonify({
        'stats': {
            'revenue': float(revenue),
            'net_sales': float(net_sales),
            'total_discount': float(total_discount),
            'void_amount': float(void_amount),
            'void_qty': int(void_qty),
            'cancelled_count': int(cancelled_count),
            'top_payment_method_count': top_pm_count,
            'top_payment_method_sales': top_pm_sales,
            'payment_breakdown': breakdown,
            'active_guests': int(active_guests),
            'total_guests_today': int(total_guests_today),
            'occupied': int(occupied_tables),
            'transactions': int(total_txns)
        },
        'charts': {
            'trend': trend, 
            'hourly_sales': hourly_sales,
            'category_sales': category_sales,
            'top_items': top_items,
            'type_performance': type_performance,
            'top_waiters': top_waiters
        }
    })

@app.route('/api/manager/employees', methods=['GET'])
def get_employees():
    conn, cursor = get_db()
    cursor.execute("SELECT id, employee_id, firstName, lastName, position, contact_number FROM employee_management")
    employees = cursor.fetchall()
    cursor.close()
    return jsonify(employees)

@app.route('/api/manager/inventory', methods=['GET'])
def get_inventory():
    conn, cursor = get_db()
    cursor.execute("SELECT menu_id, menu_name, category, unit_price, availability, type FROM main_menu_management")
    items = cursor.fetchall()
    cursor.close()
    return jsonify(items)

@app.route('/manager')
def manager_dashboard():
    if session.get('role') != 'manager':
        return redirect(url_for('index'))
    return render_template('manager.html')

@app.route('/api/manager/menu/save', methods=['POST'])
def save_menu_item():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    try:
        conn, cursor = get_db()
        if data.get('id'):
            cursor.execute("""
                UPDATE main_menu_management 
                SET menu_name=%s, category=%s, unit_price=%s, availability=%s, type=%s 
                WHERE menu_id=%s
            """, (data['name'], data['category'], data['price'], data['stock'], data['type'], data['id']))
        else:
            printer_id = 1 if data['type'] == 'drinkable' else 2
            cursor.execute("""
                INSERT INTO main_menu_management (menu_name, category, unit_price, availability, type, printer_id) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (data['name'], data['category'], data['price'], data['stock'], data['type'], printer_id))
        conn.commit()
        cursor.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/manager/staff/save', methods=['POST'])
def save_staff_record():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json
    try:
        conn, cursor = get_db()
        if data.get('id'): 
            if data.get('password'): 
                cursor.execute("""
                    UPDATE employee_management 
                    SET employee_id=%s, firstName=%s, lastName=%s, position=%s, contact_number=%s, password=%s 
                    WHERE id=%s
                """, (data['emp_id'], data['fname'], data['lname'], data['position'], data['contact'], data['password'], data['id']))
            else: 
                cursor.execute("""
                    UPDATE employee_management 
                    SET employee_id=%s, firstName=%s, lastName=%s, position=%s, contact_number=%s 
                    WHERE id=%s
                """, (data['emp_id'], data['fname'], data['lname'], data['position'], data['contact'], data['id']))
        else:
            cursor.execute("""
                INSERT INTO employee_management (employee_id, firstName, lastName, position, contact_number, password) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (data['emp_id'], data['fname'], data['lname'], data['position'], data['contact'], data['password']))
        conn.commit()
        cursor.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/manager/transactions_history', methods=['GET'])
def get_tx_history():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    
    query = """
        SELECT t.id, t.transaction_code, t.guest_name, t.contact_number, t.guest_email, t.status, t.created_at, t.guest_count,
               GROUP_CONCAT(DISTINCT tb.table_name SEPARATOR ', ') as table_summary,
               r.total_amount, r.amount_paid as total_paid, r.change_amount, r.payment_summary as payment_method,
               (
                   SELECT SUM(o.total_price) 
                   FROM order_items o 
                   WHERE o.transaction_id = t.id AND o.status != 'void'
               ) as gross_items,
               (
                   SELECT SUM(o.total_price) 
                   FROM order_items o 
                   JOIN main_menu_management m ON o.menu_id = m.menu_id 
                   WHERE o.transaction_id = t.id AND o.status != 'void' AND m.type = 'solid'
               ) as food_sales,
               (
                   SELECT SUM(o.total_price) 
                   FROM order_items o 
                   JOIN main_menu_management m ON o.menu_id = m.menu_id 
                   WHERE o.transaction_id = t.id AND o.status != 'void' AND m.type = 'drinkable'
               ) as drinkable_sales
        FROM transactions t
        LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
        LEFT JOIN tables tb ON tt.table_id = tb.id
        LEFT JOIN receipts r ON t.id = r.transaction_id
        WHERE t.status IN ('paid', 'cancelled', 'merged')
    """
    params = []
    
    if from_date and to_date:
        query += " AND DATE(t.created_at) BETWEEN %s AND %s"
        params.extend([from_date, to_date])
    elif from_date:
        query += " AND DATE(t.created_at) >= %s"
        params.append(from_date)
    elif to_date:
        query += " AND DATE(t.created_at) <= %s"
        params.append(to_date)
        
    query += " GROUP BY t.id ORDER BY t.created_at DESC"
    
    conn, cursor = get_db()
    cursor.execute(query, tuple(params))
    history = cursor.fetchall()
    
    history_data = []
    for row in history:
        gross = float(row['gross_items'] or 0)
        expected = gross + (gross * get_service_charge_rate())
        actual = float(row['total_amount'] or 0)
        
        discount = round(expected - actual, 2) if row['status'] == 'paid' else 0.0
        if discount < 0: discount = 0.0
        row['discount'] = discount
        
        row['guest_count'] = row['guest_count'] or 0
        row['food_sales'] = float(row['food_sales'] or 0)
        row['drinkable_sales'] = float(row['drinkable_sales'] or 0)
        
        pm = str(row['payment_method'] or 'N/A')
        row['clean_payment_method'] = pm.split(' - ')[0] if ' - ' in pm else pm
        if row['status'] != 'paid':
            row['clean_payment_method'] = '--'
            
        history_data.append(row)

    cursor.close()
    return jsonify(history_data)

@app.route('/api/manager/transaction_files/<txn_code>', methods=['GET'])
def get_txn_files(txn_code):
    if session.get('role') != 'manager':
        return jsonify({'success': False}), 403
        
    files_found = []
    folders = ['Official_Receipts', 'free_receipts', 'void_receipts', 'pre_receipts', 'specific_receipts']
    
    for folder in folders:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                if txn_code in filename and filename.endswith('.txt'):
                    files_found.append({
                        'folder': folder,
                        'filename': filename,
                        'type': folder.replace('_', ' ').title()
                    })
                    
    conn, cursor = get_db()
    
    cursor.execute("""
        SELECT o.quantity, o.unit_price, o.total_price, m.menu_name, o.status 
        FROM order_items o 
        JOIN main_menu_management m ON o.menu_id = m.menu_id 
        JOIN transactions t ON o.transaction_id = t.id
        WHERE t.transaction_code = %s
    """, (txn_code,))
    items = cursor.fetchall()
    
    cursor.execute("""
        SELECT t.*, GROUP_CONCAT(DISTINCT tb.table_name SEPARATOR ', ') as table_summary
        FROM transactions t
        LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
        LEFT JOIN tables tb ON tt.table_id = tb.id
        WHERE t.transaction_code = %s
        GROUP BY t.id
    """, (txn_code,))
    txn = cursor.fetchone()
    
    cursor.close()

    return jsonify({
        'success': True, 
        'files': files_found, 
        'items': items, 
        'transaction': txn
    })

@app.route('/download_receipt/<folder>/<filename>')
def download_receipt_file(folder, filename):
    if session.get('role') != 'manager':
        return "Unauthorized", 403
        
    allowed_folders = ['Official_Receipts', 'free_receipts', 'void_receipts', 'pre_receipts', 'specific_receipts']
    if folder not in allowed_folders:
        return "Invalid folder", 400
        
    return send_from_directory(folder, filename, as_attachment=True)

@app.route('/api/manager/reprint_file', methods=['POST'])
def reprint_file():
    if session.get('role') != 'manager':
        return jsonify({'success': False}), 403
        
    data = request.json
    folder = data.get('folder')
    filename = data.get('filename')
    
    if folder not in ['Official_Receipts', 'free_receipts', 'void_receipts', 'pre_receipts', 'specific_receipts']:
        return jsonify({'success': False, 'message': 'Invalid folder'})
        
    file_path = os.path.join(folder, filename)
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'message': 'File not found on server'})
        
    target_split_name = None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            if "This Receipt belongs to :" in file_content:
                target_split_name = file_content.split(">> ")[1].split("\n")[0].strip()
    except:
        pass

    raw_text = ""

    if folder == 'Official_Receipts':
        try:
            parts = filename.split('_')
            txn_code = parts[1] if len(parts) > 1 else None

            conn, cursor = get_db()
            
            cursor.execute('''
                SELECT t.*, GROUP_CONCAT(DISTINCT tb.table_name SEPARATOR ', ') as assigned_tables
                FROM transactions t
                LEFT JOIN transaction_tables tt ON t.id = tt.transaction_id
                LEFT JOIN tables tb ON tt.table_id = tb.id
                WHERE t.transaction_code = %s
                GROUP BY t.id
            ''', (txn_code,))
            txn = cursor.fetchone()

            if txn:
                tx_id = txn['id']
                
                cursor.execute('''
                    SELECT o.quantity, o.unit_price, o.total_price, m.menu_name 
                    FROM order_items o 
                    JOIN main_menu_management m ON o.menu_id = m.menu_id 
                    WHERE o.transaction_id = %s AND o.status != "void"
                ''', (tx_id,))
                items = cursor.fetchall()
                
                cursor.execute('SELECT amount, payment_method, reference_number FROM payments WHERE transaction_id = %s ORDER BY id DESC LIMIT 1', (tx_id,))
                payment = cursor.fetchone()
                if not payment:
                    payment = {'payment_method': 'CASH', 'amount': 0, 'reference_number': 'N/A'}

                cursor.execute("SELECT total_amount, amount_paid, change_amount, printed_by FROM receipts WHERE transaction_id = %s ORDER BY id DESC LIMIT 1", (tx_id,))
                receipt_record = cursor.fetchone()

                subtotal = float(sum(i['total_price'] for i in items))
                sc = round(subtotal * get_service_charge_rate(), 2)
                vatable = round(subtotal / 1.12, 2)
                vat = round(subtotal - vatable, 2)
                discount = 0.0 

                if receipt_record:
                    grand_total = float(receipt_record['total_amount'])
                    tendered = float(receipt_record['amount_paid'])
                    change = float(receipt_record['change_amount'])
                    cashier_id = receipt_record['printed_by']
                    
                    cursor.execute("SELECT firstName, lastName FROM employee_management WHERE id = %s", (cashier_id,))
                    emp = cursor.fetchone()
                    cashier_name = f"{emp['firstName']} {emp['lastName']}" if emp else "Cashier"
                else:
                    grand_total = round(subtotal + sc, 2)
                    tendered = grand_total
                    change = 0.0
                    cashier_name = session.get('name', 'Cashier')
                    
                payment['tendered'] = tendered
                payment['change'] = change
                payment['method'] = payment.get('payment_method', 'CASH')
                
                cursor.execute("SELECT id, split_name, split_type, amount FROM bill_splits WHERE transaction_id = %s", (tx_id,))
                all_splits = cursor.fetchall()
                
                split_data = None
                if all_splits:
                    target_split = all_splits[0]
                    
                    if target_split_name:
                        for s in all_splits:
                            if target_split_name in s['split_name'] or s['split_name'] in target_split_name:
                                target_split = s
                                break
                    
                    split_items = []
                    if target_split['split_type'] == 'items':
                        cursor.execute('''
                            SELECT bsi.quantity, (bsi.quantity * o.unit_price) as total_price, m.menu_name 
                            FROM bill_split_items bsi
                            JOIN order_items o ON bsi.order_item_id = o.id
                            JOIN main_menu_management m ON o.menu_id = m.menu_id
                            WHERE bsi.split_id = %s
                        ''', (target_split['id'],))
                        split_items = cursor.fetchall()
                        
                    split_data = {
                        'split_type': target_split['split_type'],
                        'split_name': target_split['split_name'],
                        'amount': float(target_split['amount']),
                        'split_items': split_items
                    }
                
                raw_text = generate_official_receipt_reprint_text(
                    txn, items, subtotal, discount, sc, vatable, vat, 
                    grand_total, payment, cashier_name,
                    split_data=split_data, all_splits=all_splits
                )
            cursor.close()
        except Exception as e:
            print(f"Error rebuilding reprint receipt: {e}")
            
    if not raw_text:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
            raw_text = raw_text.replace("\x1b\x70\x00\x19\xfa", "")
            
    reprint_dir = "Reprint"
    os.makedirs(reprint_dir, exist_ok=True)
    reprint_path = os.path.join(reprint_dir, f"REPRINT_{filename}")
    try:
        with open(reprint_path, 'w', encoding='utf-8') as rf:
            rf.write(raw_text)
        folder_msg = "Reprint copy saved to 'reprint' folder! "
    except Exception as e:
        folder_msg = ""
        
    conn, cursor = get_db()
    cursor.execute("SELECT ip_address FROM kitchen_printer WHERE name = 'CASHIER'")
    printer = cursor.fetchone()
    cursor.close()
    
    if printer and printer['ip_address']:
        success = print_to_escpos(raw_text, printer['ip_address'])
        if success:
            return jsonify({'success': True, 'message': folder_msg + 'Receipt sent to printer.'})
        return jsonify({'success': False, 'message': folder_msg + 'Failed to connect to printer.'})
        
    return jsonify({'success': True, 'message': folder_msg + 'Cashier printer IP not configured, but file was successfully generated.'})

@app.route('/api/manager/shifts', methods=['GET'])
def get_shifts():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    conn, cursor = get_db()
    cursor.execute('''
        SELECT c.id, c.employee_id, e.firstName, e.lastName, 
               c.opening_amount, c.total_cash, c.total_non_cash, 
               c.expected_cash, c.closing_amount, c.short_over, 
               c.status, c.created_at, c.closed_at
        FROM cash_drawer c
        LEFT JOIN employee_management e ON c.employee_id = e.id
        ORDER BY c.status DESC, c.created_at DESC
    ''')
    shifts = cursor.fetchall()
    cursor.close()
    return jsonify(shifts)

@app.route('/api/manager/shift/close', methods=['POST'])
def close_shift():
    if session.get('role') != 'manager':
        return jsonify({'success': False}), 403
        
    data = request.json
    shift_id = data.get('shift_id')
    closing_amount = float(data.get('closing_amount', 0))
    
    conn, cursor = get_db()
    
    cursor.execute("SELECT opening_amount FROM cash_drawer WHERE id = %s AND status = 'open'", (shift_id,))
    shift = cursor.fetchone()
    
    if not shift:
        cursor.close()
        return jsonify({'success': False, 'message': 'Shift not found or already closed.'})
        
    cursor.execute("""
        SELECT payment_method, SUM(amount) as total 
        FROM payments 
        WHERE shift_id = %s
        GROUP BY payment_method
    """, (shift_id,))
    sales = cursor.fetchall()
    
    total_cash = sum(float(s['total']) for s in sales if s['payment_method'] == 'cash')
    total_non_cash = sum(float(s['total']) for s in sales if s['payment_method'] in ['qrph', 'card'])
            
    opening = float(shift['opening_amount'])
    expected_cash = opening + total_cash
    short_over = closing_amount - expected_cash
    
    cursor.execute("""
        UPDATE cash_drawer 
        SET total_cash = %s, total_non_cash = %s, expected_cash = %s, 
            closing_amount = %s, short_over = %s, status = 'closed', closed_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (total_cash, total_non_cash, expected_cash, closing_amount, short_over, shift_id))
    
    conn.commit()
    cursor.close()
    
    return jsonify({'success': True, 'message': 'Shift closed securely with full sales breakdown.'})

@app.route('/api/manager/shift/open', methods=['POST'])
def open_shift():
    if session.get('role') != 'manager':
        return jsonify({'success': False}), 403
        
    data = request.json
    emp_id = data.get('employee_id')
    opening_amount = data.get('opening_amount', 0)
    
    conn, cursor = get_db()
    
    cursor.execute("SELECT id FROM cash_drawer WHERE employee_id = %s AND status = 'open'", (emp_id,))
    if cursor.fetchone():
        cursor.close()
        return jsonify({'success': False, 'message': 'This specific cashier already has an open shift.'})
        
    cursor.execute("INSERT INTO cash_drawer (employee_id, opening_amount, status) VALUES (%s, %s, 'open')", (emp_id, opening_amount))
    conn.commit()
    cursor.close()
    return jsonify({'success': True, 'message': 'New shift started successfully for the cashier.'})

@app.route('/api/manager/shift/active_summary/<int:shift_id>', methods=['GET'])
def get_active_shift_summary(shift_id):
    conn, cursor = get_db()
    cursor.execute("SELECT opening_amount FROM cash_drawer WHERE id = %s", (shift_id,))
    shift = cursor.fetchone()
    
    if not shift:
        cursor.close()
        return jsonify({'success': False, 'message': 'Shift not found.'})
        
    cursor.execute("""
        SELECT payment_method, SUM(amount) as total 
        FROM payments 
        WHERE shift_id = %s
        GROUP BY payment_method
    """, (shift_id,))
    
    sales = cursor.fetchall()
    cursor.close()
    
    total_cash = sum(float(s['total']) for s in sales if s['payment_method'] == 'cash')
    total_non_cash = sum(float(s['total']) for s in sales if s['payment_method'] in ['qrph', 'card'])
    expected_cash = float(shift['opening_amount']) + total_cash
    
    return jsonify({
        'success': True,
        'opening_amount': float(shift['opening_amount']),
        'total_cash_sales': total_cash,
        'total_non_cash': total_non_cash,
        'expected_cash': expected_cash
    })

@app.route('/api/manager/vouchers', methods=['GET'])
def get_vouchers():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    conn, cursor = get_db()
    cursor.execute("SELECT * FROM vouchers ORDER BY created_at DESC")
    vouchers = cursor.fetchall()
    cursor.close()
    return jsonify(vouchers)

@app.route('/api/manager/vouchers/save', methods=['POST'])
def save_voucher():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json
    try:
        conn, cursor = get_db()
        if data.get('id'):
            cursor.execute("""
                UPDATE vouchers 
                SET discount_type=%s, discount_value=%s, status=%s, max_uses=%s 
                WHERE id=%s
            """, (data['type'], data['value'], data['status'], data['max_uses'], data['id']))
        else:
            cursor.execute("""
                INSERT INTO vouchers (voucher_code, discount_type, discount_value, status, max_uses, current_uses) 
                VALUES (%s, %s, %s, %s, %s, 0)
            """, (data['code'].upper(), data['type'], data['value'], data['status'], data['max_uses']))
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Voucher saved successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Voucher code might already exist.'})

@app.route('/api/manager/vouchers/delete/<int:v_id>', methods=['DELETE'])
def delete_voucher(v_id):
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    try:
        conn, cursor = get_db()
        cursor.execute("DELETE FROM vouchers WHERE id = %s", (v_id,))
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Voucher deleted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Database error'})

@app.route('/api/validate_voucher', methods=['POST'])
def validate_voucher():
    data = request.json
    code = data.get('code', '').upper()
    
    conn, cursor = get_db()
    cursor.execute("SELECT * FROM vouchers WHERE voucher_code = %s", (code,))
    voucher = cursor.fetchone()
    cursor.close()
    
    if not voucher:
        return jsonify({'success': False, 'message': 'Invalid voucher code.'})
    if voucher['status'] == 'inactive':
        return jsonify({'success': False, 'message': 'Voucher is inactive.'})
    if voucher['status'] == 'used' or (voucher['max_uses'] > 0 and voucher['current_uses'] >= voucher['max_uses']):
        return jsonify({'success': False, 'message': 'Voucher usage limit reached.'})
        
    return jsonify({
        'success': True, 
        'discount_type': voucher['discount_type'],
        'discount_value': float(voucher['discount_value'])
    })
    
@app.route('/api/manager/categories', methods=['GET'])
def get_categories():
    if session.get('role') != 'manager':
        return jsonify([])
    conn, cursor = get_db()
    cursor.execute("SELECT category_name FROM menu_categories ORDER BY category_name")
    categories = cursor.fetchall()
    cursor.close()
    return jsonify(categories)

@app.route('/api/manager/categories/save', methods=['POST'])
def save_category():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    old_name = data.get('old_name')
    new_name = data.get('new_name')
    
    if not new_name:
        return jsonify({'success': False, 'message': 'Category name cannot be empty.'})

    try:
        conn, cursor = get_db()
        if old_name:
            cursor.execute("UPDATE menu_categories SET category_name = %s WHERE category_name = %s", (new_name, old_name))
            cursor.execute("UPDATE main_menu_management SET category = %s WHERE category = %s", (new_name, old_name))
        else:
            cursor.execute("INSERT INTO menu_categories (category_name) VALUES (%s)", (new_name,))
            
        conn.commit()
        cursor.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Category already exists or database error.'})

@app.route('/api/manager/categories/delete/<category_name>', methods=['DELETE'])
def delete_category(category_name):
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    try:
        conn, cursor = get_db()
        
        cursor.execute("SELECT COUNT(*) as count FROM main_menu_management WHERE category = %s", (category_name,))
        if cursor.fetchone()['count'] > 0:
            cursor.close()
            return jsonify({'success': False, 'message': f'Cannot delete "{category_name}". It is currently assigned to menu items.'})
            
        cursor.execute("DELETE FROM menu_categories WHERE category_name = %s", (category_name,))
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Category deleted successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Database error.'})

@app.route('/api/manager/menu/delete/<int:menu_id>', methods=['DELETE'])
def delete_menu_item(menu_id):
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    try:
        conn, cursor = get_db()
        cursor.execute("DELETE FROM main_menu_management WHERE menu_id = %s", (menu_id,))
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Menu item deleted successfully.'})
        
    except mysql.connector.Error as err:
        if err.errno == 1451:
            return jsonify({
                'success': False, 
                'message': 'Cannot delete this item because it exists in past transactions. Tip: Edit it and set Stock Availability to 0 instead!'
            })
        return jsonify({'success': False, 'message': 'Database error.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/floorplan_editor')
def floorplan_editor():
    if session.get('role') != 'manager':
        return redirect(url_for('index'))
    
    return render_template('floorplan_editor.html')

@app.route('/api/floorplan/data', methods=['GET'])
def get_floorplan_data():
    try:
        conn, cursor = get_db()
        
        cursor.execute("SELECT * FROM tables")
        tables_data = cursor.fetchall()
        tables_dict = {f"t_{t['id']}": {
            'id': t['id'], 'name': t['table_name'], 'capacity': t['capacity'], 'status': t['status'],
            'posX': t.get('pos_x', 100), 'posY': t.get('pos_y', 100), 'shape': t.get('shape', 'circle'), 
            'width': t.get('width', 64), 'height': t.get('height', 64),
            'fillColor': t.get('fill_color', '#D9C8A9'), 'strokeColor': t.get('stroke_color', '#544031'), 
            'textColor': t.get('text_color', '#544031')
        } for t in tables_data}

        cursor.execute("SELECT * FROM floorplan_elements")
        elements_data = cursor.fetchall()
        elements_dict = {f"e_{e['id']}": {
            'id': e['id'], 'elType': e['el_type'], 'shapeType': e['shape_type'],
            'posX': e['pos_x'], 'posY': e['pos_y'], 'width': e['width'], 'height': e['height'],
            'posX2': e['pos_x2'], 'posY2': e['pos_y2'], 'content': e['content'],
            'fillColor': e['fill_color'], 'strokeColor': e['stroke_color'], 'textColor': e['text_color'],
            'strokeWidth': e['stroke_width'], 'fontSize': e['font_size']
        } for e in elements_data}

        cursor.execute("SELECT setting_key, setting_value FROM system_settings WHERE setting_key IN ('floorplan_bg_image', 'color_vacant', 'color_occupied')")
        settings = {row['setting_key']: row['setting_value'] for row in cursor.fetchall()}
        
        cursor.close()
        return jsonify({'success': True, 'tables': tables_dict, 'elements': elements_dict, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manager/floorplan/bulk_save', methods=['POST'])
def bulk_save_floorplan():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    try:
        conn, cursor = get_db()
        
        for t in data.get('tables', []):
            if str(t['id']).startswith('temp_'):
                cursor.execute("""
                    INSERT INTO tables (table_name, capacity, pos_x, pos_y, shape, width, height, fill_color, stroke_color, text_color, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (t['name'], t['capacity'], t['posX'], t['posY'], t['shape'], t['width'], t['height'], t['fillColor'], t['strokeColor'], t['textColor'], 'vacant'))
            else:
                cursor.execute("""
                    UPDATE tables SET table_name=%s, capacity=%s, pos_x=%s, pos_y=%s, shape=%s, width=%s, height=%s, fill_color=%s, stroke_color=%s, text_color=%s
                    WHERE id=%s
                """, (t['name'], t['capacity'], t['posX'], t['posY'], t['shape'], t['width'], t['height'], t['fillColor'], t['strokeColor'], t['textColor'], t['id']))

        for e in data.get('elements', []):
            if str(e['id']).startswith('temp_'):
                cursor.execute("""
                    INSERT INTO floorplan_elements (el_type, shape_type, pos_x, pos_y, width, height, pos_x2, pos_y2, content, fill_color, stroke_color, text_color, stroke_width, font_size)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (e.get('elType'), e.get('shapeType'), e.get('posX'), e.get('posY'), e.get('width'), e.get('height'), e.get('posX2'), e.get('posY2'), e.get('content'), e.get('fillColor'), e.get('strokeColor'), e.get('textColor'), e.get('strokeWidth'), e.get('fontSize')))
            else:
                cursor.execute("""
                    UPDATE floorplan_elements SET el_type=%s, shape_type=%s, pos_x=%s, pos_y=%s, width=%s, height=%s, pos_x2=%s, pos_y2=%s, content=%s, fill_color=%s, stroke_color=%s, text_color=%s, stroke_width=%s, font_size=%s
                    WHERE id=%s
                """, (e.get('elType'), e.get('shapeType'), e.get('posX'), e.get('posY'), e.get('width'), e.get('height'), e.get('posX2'), e.get('posY2'), e.get('content'), e.get('fillColor'), e.get('strokeColor'), e.get('textColor'), e.get('strokeWidth'), e.get('fontSize'), e['id']))

        for t_id in data.get('deletedTables', []):
            cursor.execute("DELETE FROM tables WHERE id = %s", (t_id,))
        for e_id in data.get('deletedElements', []):
            cursor.execute("DELETE FROM floorplan_elements WHERE id = %s", (e_id,))

        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'message': 'Layout saved securely.'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/manager/floorplan/upload_image', methods=['POST'])
def upload_design_image():
    if session.get('role') != 'manager':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image provided'}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400
        
    if file:
        filename = secure_filename(file.filename)
        unique_filename = f"design_{int(datetime.now().timestamp())}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        return jsonify({'success': True, 'path': f"/static/uploads/{unique_filename}"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)