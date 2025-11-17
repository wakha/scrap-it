# 🛒 Scrap-It

**Intelligent E-commerce Data Scraping Pipeline**

An advanced, adaptive web scraping system designed for e-commerce websites with automatic product discovery, universal selector detection, bot protection analysis, and comprehensive shipping information extraction.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 🌟 Key Features

### Core Capabilities
- **🔍 Automatic Product Discovery** - Intelligently finds products without manual configuration
- **🧭 Smart Category Navigation** - Automatically explores category pages when homepage has no products
- **🎯 Universal Selector Detection** - Adapts to any e-commerce site structure dynamically
- **🚢 Shipping Information Extraction** - Detects shipping costs, providers, and delivery options
- **🤖 Bot Protection Analysis** - Identifies CAPTCHAs, rate limits, and anti-scraping measures
- **📋 robots.txt Compliance** - Respects website policies and crawl delays
- **🐳 Docker Ready** - Full containerization with MySQL database and API

### Intelligence Features
- **Adaptive Selectors** - Learns from page structure in real-time
- **Multi-Language Support** - Works with international e-commerce sites
- **Screenshot Capture** - Visual debugging with automatic screenshots
- **Comprehensive Logging** - Detailed logs for troubleshooting and analysis
- **RESTful API** - Query scraped data via FastAPI endpoints

## 📋 Table of Contents

- [Architecture Overview](#-architecture-overview)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Pipeline Flow](#-pipeline-flow)
- [Project Structure](#-project-structure)
- [API Documentation](#-api-documentation)
- [Running the Scraper](#-running-the-scraper)
- [Configuration](#-configuration)
- [Data Access](#-data-access)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)

---

## 🏗️ Architecture Overview

The system follows a modular, service-oriented architecture with three main components:

```
┌─────────────────────────────────────────────────────────────┐
│                     Scrap-It Pipeline                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Analyzer   │───▶│   Scraper   │───▶│     ETL     │     │
│  │   Service   │    │   Service   │    │   Service   │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│        │                   │                   │             │
│        ▼                   ▼                   ▼             │
│  ┌──────────────────────────────────────────────────┐       │
│  │           Analysis → Scraped → Processed         │       │
│  │              (Pydantic Schemas)                  │       │
│  └──────────────────────────────────────────────────┘       │
│                            │                                 │
│                            ▼                                 │
│                  ┌──────────────────┐                        │
│                  │  MySQL Database  │                        │
│                  └──────────────────┘                        │
│                            │                                 │
│                            ▼                                 │
│                  ┌──────────────────┐                        │
│                  │   FastAPI REST   │                        │
│                  └──────────────────┘                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Service Components

1. **Analyzer Service** (`src.services.analyzer_service`)
   - Analyzes website structure and bot protection
   - Detects product pages, category pages, and checkout flows
   - Identifies CAPTCHAs, rate limiting, and blocking
   - Generates `AnalysisResult` schema

2. **Scraper Service** (`src.services.scraper_service`)
   - Extracts product data using adaptive selectors
   - Handles pagination and category navigation
   - Captures shipping information and options
   - Generates `ScrapedProduct` schema

3. **ETL Service** (`src.services.etl_service`)
   - Transforms and validates scraped data
   - Stores data in MySQL database
   - Generates `ProcessedProduct` schema
   - (Future: Publishes to Kafka topics)

4. **API Service** (`src.api.main`)
   - RESTful API for querying scraped data
   - Endpoints for products, shipping, sessions, and statistics
   - Swagger/OpenAPI documentation

## 🔧 Prerequisites

### Required Software
- **Docker** (20.10+) and **Docker Compose** (1.29+)
- **Git** for cloning the repository
- **4GB RAM** minimum (8GB recommended)
- **Python 3.11+** (for local development only)

### Supported Platforms
- ✅ Windows 10/11
- ✅ macOS 11+
- ✅ Linux (Ubuntu 20.04+, Debian, RHEL)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/scrap-it.git
cd scrap-it/scrap-services
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your preferred settings (optional)
# Default settings work out of the box
```

**Key Environment Variables:**
```env
# Database Configuration
DB_HOST=db/localhost
DB_PORT=3306
DB_NAME=your_db_name
DB_USER=your_user_name
DB_PASSWORD=your_secure_password

# API Configuration
API_KEY=your_secret_api_key
API_HOST=0.0.0.0
API_PORT=8000

# Scraper Configuration
HEADLESS=True
SCREENSHOT_ENABLED=True
SCRAPE_DELAY=2
```

### 3. Start the Services

```bash
# Build and start all services (database, scraper, API)
docker-compose up -d

# Check service health
docker-compose ps

# Expected output:
# NAME                  STATUS              PORTS
# scraper_db_1          Up (healthy)        3306/tcp
# scraper_api_1         Up (healthy)        0.0.0.0:8000->8000/tcp
```

### 4. Verify API is Running

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","timestamp":"2025-11-17T10:30:00.000Z"}

# Access Swagger UI
# Open browser: http://localhost:8000/docs
```

### 5. Run Your First Scrape

```bash
# Scrape a single e-commerce site
docker-compose run --rm scraper python -m src.main --urls "https://www.matas.dk"

# Scrape multiple sites
docker-compose run --rm scraper python -m src.main --urls \
  "https://www.matas.dk" \
  "https://www.jollyroom.dk"
```

### 6. Query the Data

```bash
# Get all products (with API key from .env)
curl -H "X-API-Key: your_secret_api_key" \
  "http://localhost:8000/products?limit=10"

# Search for specific products
curl -H "X-API-Key: your_secret_api_key" \
  "http://localhost:8000/products?search=laptop&min_price=100"
```

---

## 🔄 Pipeline Flow

### Current Architecture (Synchronous)

```
┌─────────────────────────────────────────────────────────────────┐
│                      Scraping Pipeline                           │
└─────────────────────────────────────────────────────────────────┘

1️⃣  INPUT: URL(s)
    ↓
2️⃣  ANALYZER SERVICE
    • Checks robots.txt
    • Analyzes page structure
    • Detects bot protection (CAPTCHA, rate limiting)
    • Identifies product/category pages
    ↓
    Output: AnalysisResult (Pydantic Schema)
    ├─ is_scrapable: bool
    ├─ has_products: bool
    ├─ has_captcha: bool
    ├─ category_links: List[str]
    └─ detected_selectors: Dict
    ↓
3️⃣  SCRAPER SERVICE (if scrapable)
    • Navigates to product pages
    • Extracts product data (title, price, images, etc.)
    • Captures shipping information
    • Handles pagination
    • Takes screenshots for debugging
    ↓
    Output: ScrapedProduct (Pydantic Schema)
    ├─ title: str
    ├─ price: float
    ├─ currency: str
    ├─ url: str
    ├─ images: List[str]
    ├─ shipping_providers: List[ShippingProvider]
    └─ metadata: Dict
    ↓
4️⃣  ETL SERVICE
    • Validates data quality
    • Transforms to database schema
    • Stores in MySQL
    • Logs success/failure
    ↓
    Output: ProcessedProduct (Pydantic Schema)
    └─ Stored in database with timestamp, source tracking
    ↓
5️⃣  API SERVICE
    • Exposes data via REST endpoints
    • Provides search, filtering, pagination
    • Returns JSON responses
```

### Future Architecture (Event-Driven with Kafka)

```
┌────────────────────────────────────────────────────────────────┐
│              Event-Driven Pipeline (Future)                     │
└────────────────────────────────────────────────────────────────┘

URL Input
    ↓
[Analyzer Service] → Kafka Topic: "analysis-results"
    ↓
[Scraper Service] → Kafka Topic: "scraped-products"
    ↓
[ETL Service] → Kafka Topic: "processed-products"
    ↓
[Consumer Services]
    ├─ Analytics Dashboard
    ├─ Notification Service
    ├─ Data Export Service
    └─ ML Training Pipeline
```

### Data Flow Diagram

```
URL ──▶ Analyzer ──▶ AnalysisResult
                          │
                          ├─ is_scrapable = true ──▶ Scraper ──▶ ScrapedProduct ──▶ ETL ──▶ Database
                          │                                                                      │
                          │                                                                      ▼
                          │                                                                   API ◀── User Query
                          │
                          └─ is_scrapable = false ──▶ Log Blocking Reason ──▶ scraper_logs table
```

---

## 📁 Project Structure

```
scrap-it/
├── README.md                          # This file
├── scrap-services/                    # Main service directory
│   ├── docker-compose.yml             # Docker orchestration
│   ├── Dockerfile                     # Container definition
│   ├── requirements.txt               # Python dependencies
│   ├── .env.example                   # Environment template
│   ├── .pylintrc                      # Code quality config
│   │
│   ├── src/                           # Source code
│   │   ├── main.py                    # Entry point
│   │   ├── config.py                  # Configuration management
│   │   ├── constants.py               # Global constants
│   │   │
│   │   ├── services/                  # Business logic services
│   │   │   ├── analyzer_service.py    # Website analysis
│   │   │   ├── scraper_service.py     # Data extraction
│   │   │   └── etl_service.py         # Data transformation & storage
│   │   │
│   │   ├── api/                       # REST API
│   │   │   └── main.py                # FastAPI application
│   │   │
│   │   ├── database/                  # Database layer
│   │   │   ├── config.py              # DB connection
│   │   │   ├── models.py              # SQLAlchemy models
│   │   │   └── init.sql               # Database schema
│   │   │
│   │   ├── schemas/                   # Pydantic data models
│   │   │   └── messages.py            # AnalysisResult, ScrapedProduct, etc.
│   │   │
│   │   ├── helpers/                   # Utility modules
│   │   │   ├── analyzer_helpers.py    # Analysis utilities
│   │   │   ├── scraper_helpers.py     # Scraping utilities
│   │   │   ├── validation_helpers.py  # Data validation
│   │   │   └── scraper_log_helpers.py # Logging utilities
│   │   │
│   │   └── utils/                     # Core utilities
│   │       ├── logger.py              # Logging configuration
│   │       └── extractors.py          # Data extraction utilities
│   │
│   ├── logs/                          # Application logs
│   ├── screenshots/                   # Debug screenshots
│   └── data/                          # Temporary data storage
│
├── IaC/                               # Infrastructure as Code
│   ├── terraform/                     # Terraform configs (future)
│   └── kubernetes/                    # K8s manifests (future)
│
└── .github/                           # GitHub workflows
    └── workflows/
        └── code-quality.yml           # CI/CD pipeline
```

## 📡 API Documentation

The project includes a comprehensive REST API built with FastAPI for querying scraped data.

### Starting the API

The API starts automatically with `docker-compose up -d` and runs on **port 8000**.

```bash
# Check API health
curl http://localhost:8000/health

# Response: {"status":"healthy","timestamp":"2025-11-17T10:30:00Z"}
```

### Interactive Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Authentication

All endpoints (except `/health`) require an API key passed in the `X-API-Key` header.

```bash
# Set API_KEY in your .env file
API_KEY=your_secret_api_key_here
```

### Available Endpoints

#### 🛍️ Products

**Get all products (with pagination)**
```bash
GET /products?skip=0&limit=10

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/products?skip=0&limit=10"
```

**Get product by ID**
```bash
GET /products/{product_id}

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/products/1"
```

**Search products**
```bash
GET /products?search={query}&min_price={min}&max_price={max}&source={source}

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/products?search=laptop&min_price=100&max_price=2000&source=example.com"
```

**Query Parameters:**
- `skip` (int): Number of records to skip (pagination)
- `limit` (int): Max records to return (default: 100, max: 1000)
- `search` (str): Search in title and description
- `min_price` (float): Minimum price filter
- `max_price` (float): Maximum price filter
- `source` (str): Filter by source domain
- `currency` (str): Filter by currency code

#### 🚢 Shipping Information

**Get all shipping providers**
```bash
GET /shipping?skip=0&limit=50

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/shipping"
```

**Get shipping for specific product**
```bash
GET /shipping/{product_id}

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/shipping/123"
```

#### 📊 Statistics

**Get overall statistics**
```bash
GET /stats

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/stats"
```

**Response:**
```json
{
  "total_products": 1543,
  "total_sources": 12,
  "total_sessions": 45,
  "successful_scrapes": 38,
  "failed_scrapes": 7,
  "total_shipping_options": 423,
  "average_price": 299.99,
  "currency_distribution": {
    "USD": 850,
    "EUR": 693
  }
}
```

#### 📝 Scraping Sessions

**Get all scraping sessions**
```bash
GET /sessions?skip=0&limit=20

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/sessions"
```

**Get session by ID**
```bash
GET /sessions/{session_id}

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/sessions/abc-123-def"
```

#### 🏷️ Sources

**Get unique product sources**
```bash
GET /sources

curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/sources"
```

### Response Format

All successful responses follow this structure:

```json
{
  "data": [...],
  "total": 100,
  "skip": 0,
  "limit": 10
}
```

Error responses:

```json
{
  "detail": "Error message here"
}
```

### Rate Limiting

- Default: 100 requests per minute per API key
- Contact admin for increased limits

---

## 🎯 Running the Scraper

### Docker Mode (Recommended)

#### Basic Usage

**Scrape a single website:**
```bash
docker-compose run --rm scraper python -m src.main --urls "https://example.com"
```

**Scrape multiple websites:**
```bash
docker-compose run --rm scraper python -m src.main --urls \
  "https://site1.com" \
  "https://site2.com" \
  "https://site3.com"
```

#### Real-World Examples

```bash
# Danish e-commerce sites
docker-compose run --rm scraper python -m src.main --urls \
  "https://www.matas.dk" \
  "https://www.jollyroom.dk"

# International sites
docker-compose run --rm scraper python -m src.main --urls \
  "https://www.amazon.com" \
  "https://www.ebay.com"
```

#### Advanced Options

**With specific product pages:**
```bash
docker-compose run --rm scraper python -m src.main \
  --urls "https://example.com" \
  --product-path "/products/laptop-123"
```

**With checkout path:**
```bash
docker-compose run --rm scraper python -m src.main \
  --urls "https://example.com" \
  --product-path "/products/laptop-123" \
  --checkout-path "/checkout"
```

**Custom configuration:**
```bash
docker-compose run --rm scraper python -m src.main \
  --urls "https://example.com" \
  --headless false \
  --timeout 60000 \
  --max-retries 5
```

### Local Development Mode

For development and debugging, you can run the scraper locally without Docker.

#### Setup

1. **Create virtual environment**
   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # Linux/macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   cd scrap-services
   pip install -r requirements.txt
   
   # Install Playwright browsers
   playwright install chromium
   ```

3. **Setup local MySQL database**
   ```bash
   # Install MySQL 8.0
   # Create database
   mysql -u root -p < src/database/init.sql
   
   # Update .env with local DB credentials
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=scraper_db
   DB_USER=scraper_user
   DB_PASSWORD=your_password
   ```

4. **Run scraper**
   ```bash
   python -m src.main --urls "https://example.com"
   ```

### Command-Line Arguments

```
python -m src.main [OPTIONS]

Options:
  --urls TEXT              One or more URLs to scrape [required]
  --product-path TEXT      Specific product page path (optional)
  --checkout-path TEXT     Specific checkout page path (optional)
  --headless BOOLEAN       Run browser in headless mode (default: true)
  --timeout INTEGER        Page load timeout in ms (default: 30000)
  --max-retries INTEGER    Max retry attempts (default: 3)
  --help                   Show this message and exit
```

### Output

The scraper generates several outputs:

1. **Console Logs** - Real-time progress and status
   ```
   ==========================================
   STEP 1: Website Analysis
   ==========================================
   [OK] robots.txt allows scraping
   [OK] Products detected on homepage
   [OK] No CAPTCHA or blocking detected
   
   ==========================================
   STEP 2: Product Scraping
   ==========================================
   [OK] Found 15 products
   [OK] Extracted shipping information
   
   ==========================================
   STEP 3: ETL Processing & Storage
   ==========================================
   [OK] Saved product: Laptop XYZ ($999.99)
   ```

2. **Log Files** - Stored in `logs/scraper_YYYYMMDD.log`

3. **Screenshots** - Saved in `screenshots/` directory
   - `analysis_{domain}_{timestamp}.png`
   - `product_{product_id}_{timestamp}.png`

4. **Database Records** - Stored in MySQL
   - `products` table
   - `shipping_providers` table
   - `scraper_logs` table

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the `scrap-services` directory:

```env
# ==========================================
# Database Configuration
# ==========================================
DB_HOST=db                              # Database host (use 'localhost' for local dev)
DB_PORT=3306                            # MySQL port
DB_NAME=scraper_db                      # Database name
DB_USER=scraper_user                    # Database user
DB_PASSWORD=secure_password_here        # Database password

# ==========================================
# API Configuration
# ==========================================
API_KEY=your_secret_api_key_here        # API authentication key
API_HOST=0.0.0.0                        # API host (0.0.0.0 for all interfaces)
API_PORT=8000                           # API port

# ==========================================
# Scraper Configuration
# ==========================================
HEADLESS=true                           # Run browser in headless mode
MAX_RETRIES=3                           # Maximum retry attempts
TIMEOUT=30000                           # Page load timeout (milliseconds)
USER_AGENT=Mozilla/5.0...               # Custom user agent string
MAX_PRODUCTS_PER_PAGE=50                # Max products to scrape per page
SCREENSHOT_ON_ERROR=true                # Take screenshot on errors

# ==========================================
# Logging Configuration
# ==========================================
LOG_LEVEL=INFO                          # Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_DIR=logs                            # Log directory path
LOG_RETENTION_DAYS=30                   # Days to keep log files

# ==========================================
# Bot Protection
# ==========================================
RESPECT_ROBOTS_TXT=true                 # Respect robots.txt rules
MIN_REQUEST_DELAY=1000                  # Minimum delay between requests (ms)
RANDOM_DELAY_RANGE=2000                 # Random delay range (ms)

# ==========================================
# Feature Flags
# ==========================================
ENABLE_SHIPPING_EXTRACTION=true         # Extract shipping information
ENABLE_CATEGORY_NAVIGATION=true         # Navigate category pages
ENABLE_PAGINATION=true                  # Follow pagination links
MAX_PAGINATION_DEPTH=5                  # Maximum pagination pages to follow
```

### Selector Configuration

The scraper uses adaptive selectors defined in `src/config.py`:

```python
# Product selectors (auto-detected)
product_selectors = [
    '[itemtype*="schema.org/Product"]',
    '[class*="product"]',
    '[data-testid*="product"]',
    # ... more selectors
]

# Price selectors
price_selectors = [
    '[itemprop="price"]',
    '[class*="price"]',
    # ... more selectors
]

# Add to cart selectors
add_to_cart_selectors = [
    'button[class*="add-to-cart"]',
    '[data-testid*="add-to-cart"]',
    # ... more selectors
]
```

### Customizing Selectors

To add custom selectors for specific sites:

1. Edit `src/config.py`
2. Add selectors to the appropriate list
3. Rebuild Docker container: `docker-compose up -d --build`

---

## 💾 Data Access

### Database Access

#### Via Docker

**Connect to MySQL database:**
```bash
# Access MySQL shell
docker-compose exec db mysql -u scraper_user -p scraper_db
# Enter password from your .env file
```

**View scraped data:**
```sql
-- Get all products
SELECT * FROM products ORDER BY created_at DESC LIMIT 10;

-- Get products with shipping info
SELECT p.*, sp.provider_name, sp.cost, sp.delivery_time
FROM products p
LEFT JOIN shipping_providers sp ON p.id = sp.product_id
WHERE p.source LIKE '%matas%'
ORDER BY p.created_at DESC;

-- Get scraping statistics
SELECT 
    source,
    COUNT(*) as product_count,
    AVG(price) as avg_price,
    MIN(price) as min_price,
    MAX(price) as max_price
FROM products
GROUP BY source;

-- Get recent scraping sessions
SELECT * FROM scraper_logs 
ORDER BY started_at DESC 
LIMIT 20;

-- Check for blocked/failed scrapes
SELECT * FROM scraper_logs 
WHERE status = 'blocked' OR status = 'failed'
ORDER BY started_at DESC;
```

#### Via MySQL Client

```bash
# From your host machine
mysql -h localhost -P 3306 -u scraper_user -p scraper_db
```

### Database Schema

```sql
-- Products table
CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    price DECIMAL(10, 2),
    currency VARCHAR(10),
    url TEXT NOT NULL,
    source VARCHAR(255),
    description TEXT,
    images JSON,
    availability VARCHAR(50),
    sku VARCHAR(100),
    brand VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_source (source),
    INDEX idx_price (price),
    INDEX idx_created_at (created_at)
);

-- Shipping providers table
CREATE TABLE shipping_providers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    provider_name VARCHAR(255),
    cost DECIMAL(10, 2),
    currency VARCHAR(10),
    delivery_time VARCHAR(100),
    is_free BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    INDEX idx_product_id (product_id)
);

-- Scraper logs table
CREATE TABLE scraper_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE,
    url TEXT NOT NULL,
    source VARCHAR(255),
    status ENUM('success', 'failed', 'blocked') NOT NULL,
    products_found INT DEFAULT 0,
    error_message TEXT,
    blocking_reason VARCHAR(255),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INT,
    INDEX idx_status (status),
    INDEX idx_source (source),
    INDEX idx_started_at (started_at)
);
```

### Log Files

**View application logs:**
```bash
# Real-time logs (Docker)
docker-compose logs -f scraper

# View log file
cat scrap-services/logs/scraper_20251117.log

# Search logs for errors
grep -i error scrap-services/logs/scraper_*.log

# Search for specific domain
grep -i "matas.dk" scrap-services/logs/scraper_*.log
```

### Screenshots

Screenshots are automatically captured for debugging:

```bash
# List screenshots
ls -lh scrap-services/screenshots/

# Common screenshot types:
# - analysis_{domain}_{timestamp}.png    - Initial page analysis
# - product_{id}_{timestamp}.png         - Product page capture
# - error_{domain}_{timestamp}.png       - Error state capture
```

### Export Data

**Export to CSV:**
```sql
-- From MySQL
SELECT * FROM products 
INTO OUTFILE '/tmp/products.csv'
FIELDS TERMINATED BY ',' 
ENCLOSED BY '"'
LINES TERMINATED BY '\n';
```

**Export to JSON (via API):**
```bash
# Export all products
curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/products?limit=1000" \
  > products.json

# Export filtered data
curl -H "X-API-Key: your_api_key" \
  "http://localhost:8000/products?source=matas.dk&min_price=10" \
  > matas_products.json
```

---

## 🛠️ Development

### Running Tests

```bash
# Run all tests
docker-compose run --rm scraper pytest

# Run with coverage
docker-compose run --rm scraper pytest --cov=src --cov-report=html

# Run specific test file
docker-compose run --rm scraper pytest tests/test_analyzer.py

# Run with verbose output
docker-compose run --rm scraper pytest -v
```

### Code Quality

The project uses Pylint for code quality checks with GitHub Actions CI/CD.

```bash
# Run Pylint locally
cd scrap-services
pylint src/

# Run with specific configuration
pylint --rcfile=.pylintrc src/

# Check specific file
pylint src/services/scraper_service.py
```

**Quality Thresholds:**
- Pylint score: **≥ 5.0/10** (required for PR merge)
- Maintainability Index: **Informational only**

### Debugging

**Enable debug mode:**
```env
# In .env file
LOG_LEVEL=DEBUG
HEADLESS=false
SCREENSHOT_ON_ERROR=true
```

**Debug specific service:**
```bash
# Analyzer service
docker-compose run --rm scraper python -c "
from src.services.analyzer_service import AnalyzerService
import asyncio
async def test():
    analyzer = AnalyzerService()
    result = await analyzer.analyze('https://example.com')
    print(result)
asyncio.run(test())
"
```

### Adding New Features

1. **Create feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**
   - Add code to appropriate service/module
   - Update tests
   - Update documentation

3. **Test changes**
   ```bash
   # Run tests
   pytest
   
   # Check code quality
   pylint src/
   
   # Test with Docker
   docker-compose up -d --build
   ```

4. **Submit PR**
   - Ensure all tests pass
   - Pylint score ≥ 5.0
   - Update README if needed

---

## 🐳 Docker Management

### Service Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Stop and remove volumes (deletes data)
docker-compose down -v

# Restart specific service
docker-compose restart scraper

# View logs
docker-compose logs -f [service_name]

# View service status
docker-compose ps
```

### Rebuild After Changes

```bash
# Rebuild all containers
docker-compose up -d --build

# Rebuild specific service
docker-compose up -d --build scraper

# Force rebuild (no cache)
docker-compose build --no-cache
docker-compose up -d
```

### Cleanup

```bash
# Remove stopped containers
docker-compose rm

# Remove all unused Docker resources
docker system prune -a

# Remove only this project's resources
docker-compose down --rmi all --volumes --remove-orphans
```

### Database Backup & Restore

**Backup:**
```bash
# Backup to file
docker-compose exec db mysqldump -u scraper_user -p scraper_db \
  > backup_$(date +%Y%m%d).sql
```

**Restore:**
```bash
# Restore from file
docker-compose exec -T db mysql -u scraper_user -p scraper_db \
  < backup_20251117.sql
```

---
