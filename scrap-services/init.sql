-- ============================================================================
-- Database Initialization Script
-- This script creates the database and all tables if they don't exist
-- Safe to run multiple times - uses IF NOT EXISTS checks
-- ============================================================================

-- Create database if it doesn't exist
CREATE DATABASE IF NOT EXISTS scraper_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE scraper_db;

-- ============================================================================
-- PRODUCTS TABLE
-- Stores scraped product information
-- ============================================================================
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    price FLOAT NOT NULL,
    currency VARCHAR(10) NOT NULL,
    url TEXT NOT NULL,
    source_website VARCHAR(100) NOT NULL,
    scraped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    screenshot_path VARCHAR(500),
    raw_html TEXT,
    
    INDEX idx_source_website (source_website),
    INDEX idx_scraped_at (scraped_at),
    INDEX idx_title_source (title(255), source_website)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SHIPPING PROVIDERS TABLE
-- Stores shipping options for each product
-- ============================================================================
CREATE TABLE IF NOT EXISTS shipping_providers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    name VARCHAR(200) NOT NULL,
    price FLOAT,
    currency VARCHAR(10),
    delivery_time VARCHAR(200),
    delivery_type VARCHAR(50),
    description TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_product_id (product_id),
    INDEX idx_provider_name (name),
    UNIQUE KEY uq_product_provider (product_id, name),
    
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- SCRAPER LOGS TABLE
-- Tracks scraping sessions, success/failures, and bot protection
-- ============================================================================
CREATE TABLE IF NOT EXISTS scraper_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    website VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    error_message TEXT,
    products_scraped INT DEFAULT 0,
    robots_txt_allowed BOOLEAN,
    robots_txt_message VARCHAR(500),
    bot_protection_detected BOOLEAN,
    protection_types VARCHAR(500),
    protection_confidence VARCHAR(20),
    crawl_delay INT,
    
    INDEX idx_website_status (website, status),
    INDEX idx_started_at (started_at),
    INDEX idx_bot_protection (bot_protection_detected),
    INDEX idx_robots_allowed (robots_txt_allowed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- Log initialization (only if this is first run)
-- ============================================================================
INSERT IGNORE INTO scraper_logs (
    id,
    website, 
    status, 
    started_at, 
    completed_at, 
    products_scraped,
    error_message
) VALUES (
    1,
    'system',
    'success',
    NOW(),
    NOW(),
    0,
    'Database and tables initialized successfully'
);

-- ============================================================================
-- Initialization complete
-- ============================================================================
