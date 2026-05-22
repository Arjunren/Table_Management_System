# Blue Ocean Bar - Harbor Bar POS System

A professional Point of Sale (POS) and management system designed for the Blue Ocean Bar & Resto. This application streamlines restaurant operations through role-based access, real-time table management, and integrated thermal printing.

## 🚀 Core Features

### 1. Role-Based Access Control
* **Waiters:** Access to table statuses, order entry, and guest management.
* **Cashiers:** Manage active transactions, process payments, and oversee the cash drawer.
* **Managers:** High-level dashboard for shift management, menu updates, and transaction authorization (e.g., voiding items).

### 2. Table & Order Management
* **Real-time Status:** Track tables as 'vacant' or 'occupied'.
* **Table Operations:** Supports merging, splitting, and transferring tables for flexible guest seating.
* **Kitchen Workflow:** Orders are categorized as 'pending', 'preparing', or 'served', with automatic stock updates upon preparation.

### 3. Integrated Printing System
* **ESC/POS Printing:** Direct socket communication with network printers (BAR, KITCHEN, and CASHIER).
* **Automated Receipts:** Generates specialized receipts for:
    * Pre-bills for guest review.
    * Official Receipts (VATable).
    * Void slips (requires manager authorization).
    * Specific/Free item receipts.

### 4. Financial & Inventory Tracking
* **Cash Drawer Management:** Track opening/closing balances, expected vs. actual cash, and short/over calculations.
* **Payment Methods:** Supports Cash, Card, QRPH, and Split payments.
* **Menu Inventory:** Real-time tracking of item availability for both solid food and drinkable items.

## 🛠️ Tech Stack
* **Backend:** Python 3.x, Flask
* **Database:** MySQL
* **Frontend:** HTML5, Tailwind CSS, JavaScript
* **Environment:** Flask-MySQLdb, python-dotenv

## 📋 Prerequisites
* Python 3.8+
* MySQL Server
* Networked Thermal Printers (ESC/POS compatible)

## ⚙️ Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Arjunren/HarborBar_BOB.git
    cd HarborBar_BOB
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Database Setup:**
    * Import the `harbor_bar.sql` file into your MySQL server to set up tables and initial menu data.

4.  **Configuration:**
    * Create a `.env` file in the root directory and configure your credentials:
    ```env
    SECRET_KEY=
    MYSQL_HOST=localhost
    MYSQL_USER=root
    MYSQL_PASSWORD=
    MYSQL_DB=harbor_bar
    ```

5.  **Run the Application:**
    ```bash
    python app.py
    ```

## 📂 Project Structure
* `app.py`: Main Flask application and API routes.
* `harbor_bar.sql`: Database schema and initial data.
* `templates/`: HTML interfaces for different roles (cashier.html, waiter.html, etc.).
* `*_receipt.py`: Logic modules for generating various receipt types.
* `.env`: Environment configuration for security and database connection.

## 📄 License
This project is proprietary software for Arjunren Von read the license for more information.
