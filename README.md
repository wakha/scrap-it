# Scrap-It: E-Commerce Data Scraping Pipeline

A production-ready, intelligent data pipeline for scraping e-commerce websites with **automatic product discovery**, **universal selector detection**, and **bot protection analysis**.

## 🎯 Key Features

- **🤖 Automatic Product Discovery** - Just provide a domain, the system finds products automatically
- **🏷️ Smart Category Navigation** - Automatically explores categories when homepage has no products
- **🔍 Universal Selector Detection** - Works with any e-commerce site without manual configuration
- **✅ Multi-Indicator Validation** - Uses Schema.org, prices, add-to-cart buttons, and product containers
- **🛡️ Bot Protection Detection** - Analyzes Cloudflare, CAPTCHA, and other protections
- **📜 robots.txt Compliance** - Respects website policies automatically
- **🌐 Multi-language Support** - Detects buttons in 6+ languages (English, Danish, Spanish, French, German, Italian)
- **🐳 Docker Ready** - Full containerization with MySQL database
- **📸 Screenshot Capture** - Visual proof of scraping sessions

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- 4GB RAM minimum

### 1. Clone & Setup

```bash
git clone <repository>
cd scrap-it/scrap-services
cp .env.example .env
```

### 2. Run with Just a Domain

```bash
# The scraper will automatically:
# 1. Discover products on the homepage
# 2. Select a random product
# 3. Detect all necessary selectors
# 4. Scrape the product
# 5. Save to database

cd scrap-services
docker-compose run --rm scraper python -m src.main --url "http://books.toscrape.com"
```

### 3. View Results

```bash
# Check database
cd scrap-services
docker-compose exec db mysql -u scraper_user -p scraper_db
mysql> SELECT title, price FROM products;
```

## 🏗️ Architecture

### System Components

```
User provides URL (domain or product page)
      │
      ▼
┌─────────────────────────────┐
│ AnalyzerService      │ 
│ 1. Auto-discover products   │
│ 2. Detect universal selectors│
│ 3. Check robots.txt         │
│ 4. Detect bot protection    │
└─────────────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ ScraperService              │ 
│ - Dynamic configuration     │
│ - Stealth mode enabled      │
│ - Multi-step checkout flow  │
└─────────────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ ETLService                  │ 
│ - Transform & validate      │
│ - Save to MySQL database    │
└─────────────────────────────┘
```

### Service Architecture

All scraping logic is organized in **`src/services/`**:

1. **AnalyzerService** (`analyzer_service.py`)
   - `discover_product_url()` - Multi-stage product discovery:
     - STEP 1: Schema.org Product markup detection (instant validation)
     - STEP 2: Progressive selectors (high-confidence → product containers → semantic areas)
     - STEP 3: Smart URL filtering and scoring
     - STEP 4: Validate top candidates (2/4 indicators required)
     - STEP 5: Automatic category navigation fallback
   - `detect_universal_selectors()` - Detects XPath selectors for any e-commerce site
   - `analyze_website()` - Full analysis pipeline with bot detection

2. **ScraperService** (`scraper_service.py`)
   - Dynamic scraping with any configuration
   - Stealth mode with undetected-chromedriver
   - Human-like interactions (delays, mouse movements)

3. **ETLService** (`etl_service.py`)
   - Data normalization and validation
   - Deduplication
   - Database persistence

### Data Flow

```
Domain/URL Input → Discover Products → Homepage has products?
                                              │
                            ┌─────────────────┼─────────────────┐
                            │ YES             │ NO              │
                            ▼                 ▼                 │
                   Select Product     Navigate to Categories   │
                            │                 │                 │
                            │          Find Products in         │
                            │            Category Page          │
                            │                 │                 │
                            └────── Select ───┘                 │
                                     Product                     │
                                        │                        │
                                        ▼                        │
                          Detect Universal Selectors (XPath)     │
                                        │                        │
                                        ▼                        │
                   Check robots.txt → Check Bot Protection       │
                          │                  │                   │
                          ├─── Not Allowed ──┤─── STOP ──────────┤
                          │                  │                   │
                          └───── Allowed ────┴─── PROCEED ───────┘
                                                    │
                                                    ▼
                                      Scrape Product Details
                                                    │
                                                    ▼
                                      ETL → Database Storage
```

### Database Schema

```sql
products
├── id (PK)
├── title
├── price
├── currency
├── url
├── source_website
├── scraped_at
└── screenshot_path

shipping_providers
├── id (PK)
├── product_id (FK -> products.id)
├── name
├── price
├── currency
├── delivery_time
├── description
└── created_at

scraper_logs
├── id (PK)
├── website
├── status (success/failure/skipped/blocked)
├── started_at
├── completed_at
├── error_message
├── products_scraped
├── robots_txt_allowed
├── robots_txt_message
├── bot_protection_detected
├── protection_types
└── protection_confidence
```

## 💻 Usage Examples

### Scrape with Just a Domain
```bash
# System auto-discovers products and selectors
cd scrap-services
docker-compose run --rm scraper python -m src.main --url "http://books.toscrape.com"
```

### Scrape Specific Product
```bash
# Provide full product URL
cd scrap-services
docker-compose run --rm scraper python -m src.main --url "https://books.toscrape.com/catalogue/sapiens_996/index.html"
```

### With Custom Paths
```bash
# Specify product and checkout paths
cd scrap-services
docker-compose run --rm scraper python -m src.main \
  --url "https://example.com" \
  --product-path "/products/item-123" \
  --checkout-path "/checkout"
```

### Core Capabilities

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Setup & Run

1. **Clone the repository**
```bash
git clone <repository-url>
cd scrap-it
```

2. **Configure environment**
```bash
# Copy the example file to create your .env
cp .env.example .env
# Edit .env if needed (default values work for Docker)

# Copy .env to scrap-services directory (required for Docker)
cp .env scrap-services/.env
```

3. **Build and run**
```bash
cd scrap-services
docker-compose build
docker-compose up -d db  # Start database

# Wait 10 seconds for database to initialize
docker-compose run --rm scraper python -m src.main --url "http://books.toscrape.com"
```

## 🗂️ Project Structure

```
scrap-it/
├── .git/                              # Git repository
├── .gitignore                         # Git ignore rules
├── README.md                          # This file
└── scrap-services/                    # Main application
    ├── src/
    │   ├── services/                  # Core scraping services
    │   │   ├── analyzer_service.py    # Product discovery & analysis
    │   │   ├── scraper_service.py     # Dynamic scraping engine
    │   │   └── etl_service.py         # Data transformation
    │   ├── database/                  # Database models & setup
    │   ├── utils/                     # Utilities (logger, bot detector)
    │   ├── config.py                  # Configuration & settings
    │   └── main.py                    # CLI entry point
    ├── logs/                          # Scraping logs
    ├── screenshots/                   # Scraping screenshots
    ├── docker-compose.yml             # Docker orchestration
    ├── Dockerfile                     # Container definition
    ├── init.sql                       # Database initialization
    ├── .env.example                   # Environment template
    └── requirements.txt               # Python dependencies
```

## 🔑 Technical Highlights

### 🤖 Automatic Product Discovery
- Scans homepage for product links using regex patterns
- Priority-based scoring (products > categories > pagination)
- Excludes pagination and listing pages
- Randomly selects from discovered products

### 🔍 Universal Selector Detection
- Auto-detects XPath selectors for any e-commerce site
- Multi-language support (English, Danish, Spanish, French, German, Italian)
- Comprehensive fallback patterns for titles, prices, buttons
- No manual configuration required

### 🛡️ Bot Protection Analysis
- Detects: Cloudflare, CAPTCHA, DataDome, PerimeterX
- Confidence scoring (high/medium/low)
- Automated PROCEED/STOP decisions
- Detailed logging

### 📜 robots.txt Compliance
- Validates paths before scraping
- Respects crawl-delay directives
- Logs all compliance checks

## 🛠️ Development

### Local Setup

```bash
# Create virtual environment
cd scrap-services
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start database only
cd scrap-services
docker-compose up -d db
cd ..

# Run scraper locally
python -m src.main --url "http://books.toscrape.com"
```

### Environment Variables

Key settings in `.env`:

```env
# Database
DB_HOST=db
DB_PORT=3306
DB_USER=scraper_user
DB_PASSWORD=secure_password
DB_NAME=scraper_db

# Scraper
HEADLESS_MODE=true
SCREENSHOT_ENABLED=true
LOG_LEVEL=INFO
```

## 🏭 Production Considerations

### Legal & Ethical
⚠️ **Important**: This scraper respects `robots.txt` and detects bot protection. For production:
- Always check website terms of service
- Implement rate limiting
- Consider using official APIs
- Comply with GDPR/data protection laws

### Scalability Options
- **Horizontal Scaling**: Multiple scraper containers with job queue (Celery + Redis)
- **Database**: Read replicas, connection pooling, partitioning
- **Caching**: Redis for frequently accessed data
- **Async Scraping**: Playwright or Scrapy for better concurrency

### Security Hardening
- Add authentication (JWT, API keys)
- Rate limiting middleware
- HTTPS/TLS termination
- Secret management (AWS Secrets Manager, Vault)
- Database SSL connections

## 📚 Documentation

- [Usage Examples](docs/USAGE_EXAMPLES.md) - Detailed usage scenarios
- [Bot Detection](docs/BOT_DETECTION.md) - Bot protection detection guide
- [Service Architecture](src/services/README.md) - Service documentation
│       └── ci.yml              # GitHub Actions CI/CD
├── src/
│   ├── api/
│   │   ├── main.py            # FastAPI application
│   │   └── schemas.py         # Pydantic models
│   ├── database/
│   │   ├── config.py          # Database configuration
│   │   └── models.py          # SQLAlchemy models
│   ├── etl/
│   │   └── etl_service.py     # ETL service
│   ├── scraper/
│   │   └── scraper.py         # Selenium scraper
│   ├── utils/
│   │   ├── extractors.py      # XPath & regex extraction
│   │   └── logger.py          # Logging configuration
│   ├── config.py              # Application settings
│   └── main.py                # Entry point
├── tests/
│   ├── conftest.py            # Test fixtures
│   ├── test_extractors.py    # Extractor tests
│   └── test_models.py         # Model tests
├── Dockerfile                 # Container definition
├── docker-compose.yml         # Multi-container orchestration
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── .gitignore                # Git ignore rules
├── init.sql                  # Database initialization
└── README.md                 # This file
```

## 🎯 Design Decisions

### Technology Choices

**Selenium over Scrapy**:
- Needed for JavaScript-heavy sites with dynamic checkout flows
- Better for sites requiring user interactions (add to cart, checkout)
- Trade-off: Slower but more reliable for modern SPAs

**SQLAlchemy ORM over Raw SQL**:
- Type safety and IDE support
- Protection against SQL injection
- Database portability
- Trade-off: Slight performance overhead, but worth it for maintainability

**FastAPI over Flask**:
- Built-in async support for future scalability
- Automatic OpenAPI documentation
- Pydantic validation out of the box
- Modern Python type hints

**MySQL over PostgreSQL**:
- Required by assignment (commonly used at Tembi)
- Good enough for this use case
- PostgreSQL would offer better JSON support for raw_html field

### XPath vs CSS Selectors

Used XPath primarily because:
- More powerful for complex queries
- Better text matching capabilities
- Required by assignment

**Regex Usage**: Price and delivery time extraction uses regex patterns to handle various formats across different websites.

### Data Normalization

**Price Handling**:
- Store numeric value separately from currency
- Normalize comma/dot decimal separators
- Support multiple currency symbols and codes

**Text Normalization**:
- Remove extra whitespace
- Consistent formatting
- Prevents duplicate entries from formatting differences

### Error Handling

- Graceful degradation: Scraper continues if one site fails
- Detailed logging for debugging
- Database transactions ensure data consistency
- Scraper logs track success/failure metrics

## 📝 Future Enhancements

1. **Advanced Features**:
   - Price history tracking
   - Change detection and notifications
   - Multiple product selection per site
   - Product categorization and tagging

2. **Performance**:
   - Implement async scraping
   - Add caching layer
   - Database query optimization

3. **Monitoring**:
   - Prometheus metrics export
   - Grafana dashboards
   - Error rate alerting

4. **Testing**:
   - Integration tests with test containers
   - E2E API tests
   - Load testing

## 📄 License

MIT License - feel free to use this project as a reference or starting point.

## 🤝 Contributing

This is a technical assessment project, but suggestions and improvements are welcome!

---

**Built with** ❤️ **using Python, FastAPI, Selenium, SQLAlchemy, and Docker**
