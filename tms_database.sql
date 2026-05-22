-- =========================
-- DATABASE SETUP
-- =========================

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

-- =========================
-- 0. TABLES
-- =========================
CREATE TABLE IF NOT EXISTS `tables` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `table_name` VARCHAR(50) NOT NULL,
  `capacity` INT DEFAULT 4,
  `pos_x` INT DEFAULT 100,
  `pos_y` INT DEFAULT 100,
  `shape` VARCHAR(20) DEFAULT 'circle',
  `width` INT DEFAULT 64,
  `height` INT DEFAULT 64,
  `fill_color` VARCHAR(20) DEFAULT '#D9C8A9',
  `stroke_color` VARCHAR(20) DEFAULT '#544031',
  `text_color` VARCHAR(20) DEFAULT '#544031',
  `status` ENUM('vacant','occupied') DEFAULT 'vacant'
) ENGINE=InnoDB;

-- =========================
-- 1. FLOORPLAN ELEMENTS
-- =========================
CREATE TABLE IF NOT EXISTS `floorplan_elements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `el_type` VARCHAR(20) NOT NULL, 
    `shape_type` VARCHAR(20),          
    `pos_x` INT DEFAULT 0,
    `pos_y` INT DEFAULT 0,
    `width` INT DEFAULT 100,
    `height` INT DEFAULT 100,
    `pos_x2` INT DEFAULT 100,         
    `pos_y2` INT DEFAULT 100,
    `content` VARCHAR(255),
    `fill_color` VARCHAR(20) DEFAULT '#B08D6A',
    `stroke_color` VARCHAR(20) DEFAULT '#544031',
    `text_color` VARCHAR(20) DEFAULT '#544031',
    `stroke_width` INT DEFAULT 4,
    `font_size` INT DEFAULT 24
) ENGINE=InnoDB;

-- =========================
-- 2. EMPLOYEES
-- =========================
CREATE TABLE `employee_management` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `employee_id` VARCHAR(50) NOT NULL,
  `password` VARCHAR(255) NOT NULL,
  `firstName` VARCHAR(50) NOT NULL,
  `lastName` VARCHAR(50) NOT NULL,
  `contact_number` VARCHAR(20),
  `email` VARCHAR(100),
  `position` ENUM('cashier','waiter','manager')
) ENGINE=InnoDB;

INSERT INTO `employee_management`
(`employee_id`, `password`, `firstName`, `lastName`, `contact_number`, `email`, `position`)
VALUES
('EMP1000', '123456', 'Arjunren', 'Valdez', '09553750917', 'arjunrenvon@email.com', 'cashier'),
('EMP1001', '123456', 'Arjunren', 'Valdez', '09553750917', 'arjunrenvon@email.com', 'waiter'),
('EMP1002', '123456', 'Arjunren', 'Valdez', '09553750917', 'arjunrenvon@email.com', 'manager');

-- =========================
-- 3. PRINTERS
-- =========================
CREATE TABLE `kitchen_printer` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(50),
  `ip_address` VARCHAR(50)
) ENGINE=InnoDB;

INSERT INTO `kitchen_printer` (`name`,`ip_address`) VALUES
('BAR','192.168.1.250'),
('KITCHEN','192.168.1.251'),
('CASHIER','192.168.1.250');

-- =========================
-- 4. MENU
-- =========================
CREATE TABLE `main_menu_management` (
  `menu_id` INT AUTO_INCREMENT PRIMARY KEY,
  `menu_name` VARCHAR(100) NOT NULL,
  `category` VARCHAR(50),
  `unit_price` DECIMAL(10,2) NOT NULL,
  `availability` INT DEFAULT 10,
  `type` ENUM('drinkable','solid'),
  `picture_url` VARCHAR(255) DEFAULT NULL,
  `printer_id` INT,
  FOREIGN KEY (`printer_id`) REFERENCES `kitchen_printer`(`id`)
) ENGINE=InnoDB;

-- =========================
-- 5. TRANSACTIONS (MAIN BILL)
-- =========================
CREATE TABLE `transactions` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_code` VARCHAR(50) NOT NULL,
  `guest_name` VARCHAR(100),
  `contact_number` VARCHAR(20),
  `guest_email` VARCHAR(100),
  `guest_count` INT DEFAULT 1,
  `status` ENUM('open','paid','cancelled','merged') DEFAULT 'open',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- =========================
-- 6. ADDITIONAL GUEST TABLE
-- =========================
CREATE TABLE `transaction_guests` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_id` INT NOT NULL,
  `guest_name` VARCHAR(100) NOT NULL,
  `is_primary` BOOLEAN DEFAULT FALSE,
  FOREIGN KEY (`transaction_id`) REFERENCES `transactions`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =========================
-- 7. MULTI-TABLE SUPPORT
-- =========================
CREATE TABLE `transaction_tables` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_id` INT,
  `table_id` INT,
  FOREIGN KEY (`transaction_id`) REFERENCES `transactions`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`table_id`) REFERENCES `tables`(`id`)
) ENGINE=InnoDB;

-- =========================
-- 8. ORDER ITEMS (CORE)
-- =========================
CREATE TABLE `order_items` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_id` INT NOT NULL,
  `menu_id` INT NOT NULL,
  `quantity` INT NOT NULL,
  `unit_price` DECIMAL(10,2) NOT NULL,
  `total_price` DECIMAL(10,2) NOT NULL,
  `status` ENUM('pending','preparing','served','void') DEFAULT 'pending',
  `void_reason` VARCHAR(255) NULL,
  `note` VARCHAR(255) NULL,
  `waiter_name` VARCHAR(100) DEFAULT 'Unknown',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`transaction_id`) REFERENCES `transactions`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`menu_id`) REFERENCES `main_menu_management`(`menu_id`)
) ENGINE=InnoDB;

-- =========================
-- 9. OTHER SYSTEM TABLES
-- =========================
CREATE TABLE `table_transfers` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_id` INT,
  `from_table_id` INT,
  `to_table_id` INT,
  `type` ENUM('single','merge','split'),
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- =========================
-- 10. SPLITBILL
-- =========================
CREATE TABLE `bill_splits` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_id` INT,
  `split_name` VARCHAR(50),
  `split_type` ENUM('amount','items'),
  `amount` DECIMAL(10,2),
  FOREIGN KEY (`transaction_id`) REFERENCES `transactions`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =========================
-- 11. SPLITBILL BY ITEMS
-- =========================
CREATE TABLE `bill_split_items` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `split_id` INT,
  `order_item_id` INT,
  `quantity` INT DEFAULT 1,
  FOREIGN KEY (`split_id`) REFERENCES `bill_splits`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`order_item_id`) REFERENCES `order_items`(`id`)
) ENGINE=InnoDB;

-- =========================
-- 12. PAYMENTS
-- =========================
CREATE TABLE `payments` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_id` INT,
  `shift_id` INT NULL,
  `split_id` INT NULL,
  `amount` DECIMAL(10,2) NOT NULL,
  `payment_method` ENUM('cash','card','qrph','split','free'),
  `reference_number` VARCHAR(100),
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`transaction_id`) REFERENCES `transactions`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`split_id`) REFERENCES `bill_splits`(`id`)
) ENGINE=InnoDB;

-- =========================
-- 13. CASH DRAWERS
-- =========================
CREATE TABLE `cash_drawer` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `employee_id` INT,
  `opening_amount` DECIMAL(10,2),
  `closing_amount` DECIMAL(10,2),
  `status` ENUM('open','closed'),
  `total_cash` DECIMAL(10,2) DEFAULT 0,
  `total_non_cash` DECIMAL(10,2) DEFAULT 0,
  `expected_cash` DECIMAL(10,2) DEFAULT 0,
  `short_over` DECIMAL(10,2) DEFAULT 0,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  `closed_at` DATETIME NULL DEFAULT NULL,
  FOREIGN KEY (`employee_id`) REFERENCES `employee_management`(`id`)
) ENGINE=InnoDB;

-- =========================
-- 14. RECEIPTS
-- =========================
CREATE TABLE `receipts` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `transaction_id` INT,
  `receipt_number` VARCHAR(50) NOT NULL,
  `guest_name` VARCHAR(100),
  `table_summary` VARCHAR(100), 
  `total_amount` DECIMAL(10,2),
  `amount_paid` DECIMAL(10,2),
  `change_amount` DECIMAL(10,2),
  `payment_summary` TEXT, 
  `printed_by` INT,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`transaction_id`) REFERENCES `transactions`(`id`),
  FOREIGN KEY (`printed_by`) REFERENCES `employee_management`(`id`)
) ENGINE=InnoDB;

-- =========================
-- 15. RECEIPTS BY ITEMS
-- =========================
CREATE TABLE `receipt_items` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `receipt_id` INT,
  `menu_name` VARCHAR(100),
  `quantity` INT,
  `unit_price` DECIMAL(10,2),
  `total_price` DECIMAL(10,2),
  FOREIGN KEY (`receipt_id`) REFERENCES `receipts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =========================
-- 16. RECEIPTS PAYMENTS
-- =========================
CREATE TABLE `receipt_payments` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `receipt_id` INT,
  `payment_method` VARCHAR(50),
  `amount` DECIMAL(10,2),
  `reference_number` VARCHAR(100),
  FOREIGN KEY (`receipt_id`) REFERENCES `receipts`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB;

-- =========================
-- 17. VOUCHERS
-- =========================
CREATE TABLE `vouchers` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `voucher_code` VARCHAR(50) NOT NULL UNIQUE,
  `discount_type` ENUM('percentage', 'fixed') NOT NULL,
  `discount_value` DECIMAL(10,2) NOT NULL,
  `max_uses` INT DEFAULT 1,
  `current_uses` INT DEFAULT 0,
  `status` ENUM('active', 'used', 'inactive') DEFAULT 'active',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- =========================
-- 18. SYSTEM SETTINGS
-- =========================
CREATE TABLE `system_settings` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `setting_key` VARCHAR(50) NOT NULL UNIQUE,
  `setting_value` VARCHAR(255) DEFAULT NULL,
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Insert a default Service Charge of 10% (0.10) so the system has a baseline
INSERT INTO `system_settings` (`setting_key`, `setting_value`) VALUES ('service_charge_rate', '0.10');

-- =========================
-- 19. CATEGORIES
-- =========================
CREATE TABLE `menu_categories` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `category_name` VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

COMMIT;