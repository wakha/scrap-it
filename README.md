# Scrap-It

E-commerce data scraping pipeline with automatic product discovery, universal selector detection, and bot protection analysis.

## Features

- **Automatic Product Discovery** - Finds products without manual configuration
- **Smart Category Navigation** - Explores categories when homepage has no products
- **Universal Selector Detection** - Works with any e-commerce site
- **robots.txt Compliance** - Respects website policies
- **Docker Ready** - Full containerization with MySQL database

## Prerequisites

- Docker and Docker Compose installed
- 4GB RAM minimum
- Git

## Repository Setup

1. **Clone the repository**
   ```bash
   git clone <repository>
   cd scrap-it
   ```

2. **Navigate to services directory**
   ```bash
   cd scrap-services
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env file with your settings if needed
   ```

4. **Build and start Docker containers**
   ```bash
   # Start all services (database, scraper, and API)
   docker-compose up -d
   
   # Wait for database to be ready (check health status)
   docker-compose ps
   ```

## API Access

The project includes a FastAPI-based REST API for querying scraped data.

### Starting the API

The API starts automatically with `docker-compose up -d` and runs on port 8000.

**Check API health:**
```bash
curl http://localhost:8000/health
```

### API Endpoints

**Get all products (with pagination):**
```bash
curl -H "X-API-Key: your-api-key" "http://localhost:8000/products?skip=0&limit=10"
```

**Get product by ID:**
```bash
curl -H "X-API-Key: your-api-key" "http://localhost:8000/products/1"
```

**Search products:**
```bash
curl -H "X-API-Key: your-api-key" "http://localhost:8000/products?search=laptop&min_price=100&max_price=1000"
```

**Get shipping information:**
```bash
curl -H "X-API-Key: your-api-key" "http://localhost:8000/shipping"
```

**Get scraping sessions:**
```bash
curl -H "X-API-Key: your-api-key" "http://localhost:8000/sessions"
```

**Get statistics:**
```bash
curl -H "X-API-Key: your-api-key" "http://localhost:8000/stats"
```

**API Documentation:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**Note:** Set your API key in the `.env` file (`API_KEY` variable).

## Running the Scraper

### Basic Usage

**Scrape a single website:**
```bash
docker-compose run --rm scraper python -m src.main --urls "https://example.com"
```

**Scrape multiple websites:**
```bash
docker-compose run --rm scraper python -m src.main --urls "https://site1.com" "https://site2.com"
```

**Example with real sites:**
```bash
docker-compose run --rm scraper python -m src.main --urls "https://www.matas.dk" "https://www.jollyroom.dk"
```

### Without Docker (Local Development)

1. **Create virtual environment**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # or
   source .venv/bin/activate  # Linux/Mac
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup local MySQL database**
   - Install MySQL 8.0
   - Create database using `init.sql`
   - Update `.env` with local DB credentials

4. **Run scraper**
   ```bash
   python -m src.main --urls "https://example.com"
   ```

## Accessing Data

**Connect to MySQL database:**
```bash
docker-compose exec db mysql -u scraper_user -p scraper_db
# Password is in your .env file (DB_PASSWORD)
```

**View scraped data:**
```sql
SELECT * FROM products;
SELECT * FROM scraping_sessions;
```

**Check logs:**
```bash
# View real-time logs
docker-compose logs -f scraper

# View log files
cat logs/scraper.log
```

**View screenshots:**
```bash
# Screenshots are saved in the screenshots/ directory
ls screenshots/
```

## Managing Services

**Stop services:**
```bash
docker-compose down
```

**Stop and remove all data:**
```bash
docker-compose down -v
```

**Restart services:**
```bash
docker-compose restart
```

**Rebuild containers after code changes:**
```bash
docker-compose up -d --build
```
