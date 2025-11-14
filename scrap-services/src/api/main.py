"""FastAPI application for querying scraper database."""
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging

from src.database.models import Product, ShippingProvider, ScraperLog
from src.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Web Scraper API",
    description="API for querying scraped product data and shipping information",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DATABASE_URL = f"mysql+aiomysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Get database session."""
    async with AsyncSessionLocal() as session:
        yield session


def verify_api_key(x_api_key: str = Header(None)):
    """Simple API key verification."""
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include X-API-Key header."
        )
    return x_api_key


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Web Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "products": "/products",
            "product_by_id": "/products/{id}",
            "shipping": "/shipping",
            "sessions": "/sessions",
            "stats": "/stats"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(select(1))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Database connection failed")


@app.get("/products")
async def get_products(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Number of records to return"),
    website: Optional[str] = Query(None, description="Filter by source website"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price"),
    search: Optional[str] = Query(None, description="Search in product title"),
    api_key: str = Header(None, alias="X-API-Key")
):
    """Get all products with pagination and filters. Requires X-API-Key header."""
    verify_api_key(api_key)
    try:
        async with AsyncSessionLocal() as session:
            # Build query
            query = select(Product)
            
            # Apply filters
            if website:
                query = query.where(Product.source_website.like(f"%{website}%"))
            if min_price is not None:
                query = query.where(Product.price >= min_price)
            if max_price is not None:
                query = query.where(Product.price <= max_price)
            if search:
                query = query.where(Product.title.like(f"%{search}%"))
            
            # Order by most recent
            query = query.order_by(desc(Product.scraped_at))
            
            # Count total
            count_query = select(func.count()).select_from(Product)
            if website:
                count_query = count_query.where(Product.source_website.like(f"%{website}%"))
            if min_price is not None:
                count_query = count_query.where(Product.price >= min_price)
            if max_price is not None:
                count_query = count_query.where(Product.price <= max_price)
            if search:
                count_query = count_query.where(Product.title.like(f"%{search}%"))
            
            total = await session.scalar(count_query)
            
            # Apply pagination
            query = query.offset(skip).limit(limit)
            
            # Execute
            result = await session.execute(query)
            products = result.scalars().all()
            
            return {
                "total": total,
                "skip": skip,
                "limit": limit,
                "products": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "price": float(p.price),
                        "currency": p.currency,
                        "source_website": p.source_website,
                        "website_url": p.url,
                        "scraped_at": p.scraped_at.isoformat() if p.scraped_at else None
                    }
                    for p in products
                ]
            }
    except Exception as e:
        logger.error(f"Error fetching products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/products/{product_id}")
async def get_product(product_id: int):
    """Get a specific product by ID with shipping information."""
    try:
        async with AsyncSessionLocal() as session:
            # Get product
            result = await session.execute(
                select(Product).where(Product.id == product_id)
            )
            product = result.scalar_one_or_none()
            
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            
            # Get shipping providers
            shipping_result = await session.execute(
                select(ShippingProvider).where(ShippingProvider.product_id == product_id)
            )
            shipping_providers = shipping_result.scalars().all()
            
            return {
                "id": product.id,
                "title": product.title,
                "price": float(product.price),
                "currency": product.currency,
                "source_website": product.source_website,
                "website_url": product.url,
                "scraped_at": product.scraped_at.isoformat() if product.scraped_at else None,
                "screenshot_path": product.screenshot_path,
                "shipping_providers": [
                    {
                        "id": sp.id,
                        "provider_name": sp.name,
                        "delivery_type": sp.delivery_type,
                        "price": float(sp.price) if sp.price else None,
                        "currency": sp.currency,
                        "delivery_time": sp.delivery_time,
                        "description": sp.description
                    }
                    for sp in shipping_providers
                ]
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product {product_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/shipping")
async def get_shipping_providers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    delivery_type: Optional[str] = Query(None, description="Filter by delivery type"),
    provider_name: Optional[str] = Query(None, description="Filter by provider name"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum shipping price")
):
    """Get all shipping providers with filters."""
    try:
        async with AsyncSessionLocal() as session:
            # Build query
            query = select(ShippingProvider)
            
            # Apply filters
            if delivery_type:
                query = query.where(ShippingProvider.delivery_type == delivery_type)
            if provider_name:
                query = query.where(ShippingProvider.name.like(f"%{provider_name}%"))
            if max_price is not None:
                query = query.where(ShippingProvider.price <= max_price)
            
            # Count total
            count_query = select(func.count()).select_from(ShippingProvider)
            if delivery_type:
                count_query = count_query.where(ShippingProvider.delivery_type == delivery_type)
            if provider_name:
                count_query = count_query.where(ShippingProvider.name.like(f"%{provider_name}%"))
            if max_price is not None:
                count_query = count_query.where(ShippingProvider.price <= max_price)
            
            total = await session.scalar(count_query)
            
            # Apply pagination
            query = query.offset(skip).limit(limit)
            
            # Execute
            result = await session.execute(query)
            providers = result.scalars().all()
            
            return {
                "total": total,
                "skip": skip,
                "limit": limit,
                "shipping_providers": [
                    {
                        "id": sp.id,
                        "product_id": sp.product_id,
                        "provider_name": sp.name,
                        "delivery_type": sp.delivery_type,
                        "price": float(sp.price) if sp.price else None,
                        "currency": sp.currency,
                        "delivery_time": sp.delivery_time,
                        "description": sp.description
                    }
                    for sp in providers
                ]
            }
    except Exception as e:
        logger.error(f"Error fetching shipping providers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/shipping/by-website/{website_name}")
async def get_shipping_by_website(
    website_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    delivery_type: Optional[str] = Query(None, description="Filter by delivery type"),
    group_by_provider: bool = Query(False, description="Group results by provider name"),
    api_key: str = Header(None, alias="X-API-Key")
):
    """Get shipping details for all products from a specific website. Requires X-API-Key header."""
    verify_api_key(api_key)
    try:
        async with AsyncSessionLocal() as session:
            # Build query joining ShippingProvider with Product
            query = (
                select(ShippingProvider, Product)
                .join(Product, ShippingProvider.product_id == Product.id)
                .where(Product.source_website.like(f"%{website_name}%"))
            )
            
            # Apply delivery type filter
            if delivery_type:
                query = query.where(ShippingProvider.delivery_type == delivery_type)
            
            # Order by product and provider name
            query = query.order_by(Product.id, ShippingProvider.name)
            
            # Count total
            count_query = (
                select(func.count())
                .select_from(ShippingProvider)
                .join(Product, ShippingProvider.product_id == Product.id)
                .where(Product.source_website.like(f"%{website_name}%"))
            )
            if delivery_type:
                count_query = count_query.where(ShippingProvider.delivery_type == delivery_type)
            
            total = await session.scalar(count_query)
            
            if total == 0:
                return {
                    "website": website_name,
                    "total": 0,
                    "skip": skip,
                    "limit": limit,
                    "shipping_details": []
                }
            
            # Apply pagination
            query = query.offset(skip).limit(limit)
            
            # Execute
            result = await session.execute(query)
            rows = result.all()
            
            if group_by_provider:
                # Group by provider name
                provider_groups = {}
                for sp, product in rows:
                    if sp.name not in provider_groups:
                        provider_groups[sp.name] = {
                            "provider_name": sp.name,
                            "delivery_type": sp.delivery_type,
                            "occurrences": 0,
                            "price_range": {"min": None, "max": None, "currency": sp.currency},
                            "products": []
                        }
                    
                    provider_groups[sp.name]["occurrences"] += 1
                    provider_groups[sp.name]["products"].append({
                        "product_id": product.id,
                        "product_title": product.title,
                        "shipping_price": float(sp.price) if sp.price else None,
                        "delivery_time": sp.delivery_time
                    })
                    
                    # Update price range
                    if sp.price:
                        price = float(sp.price)
                        if provider_groups[sp.name]["price_range"]["min"] is None or price < provider_groups[sp.name]["price_range"]["min"]:
                            provider_groups[sp.name]["price_range"]["min"] = price
                        if provider_groups[sp.name]["price_range"]["max"] is None or price > provider_groups[sp.name]["price_range"]["max"]:
                            provider_groups[sp.name]["price_range"]["max"] = price
                
                return {
                    "website": website_name,
                    "total": total,
                    "skip": skip,
                    "limit": limit,
                    "grouped_by": "provider",
                    "shipping_providers": list(provider_groups.values())
                }
            else:
                # Return flat list
                return {
                    "website": website_name,
                    "total": total,
                    "skip": skip,
                    "limit": limit,
                    "shipping_details": [
                        {
                            "shipping_id": sp.id,
                            "product_id": product.id,
                            "product_title": product.title,
                            "product_price": float(product.price),
                            "product_currency": product.currency,
                            "provider_name": sp.name,
                            "delivery_type": sp.delivery_type,
                            "shipping_price": float(sp.price) if sp.price else None,
                            "shipping_currency": sp.currency,
                            "delivery_time": sp.delivery_time,
                            "description": sp.description
                        }
                        for sp, product in rows
                    ]
                }
    except Exception as e:
        logger.error(f"Error fetching shipping for website {website_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
async def get_scraping_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    website: Optional[str] = Query(None, description="Filter by website"),
    status: Optional[str] = Query(None, description="Filter by status (success/error)")
):
    """Get scraping sessions history."""
    try:
        async with AsyncSessionLocal() as session:
            # Build query
            query = select(ScraperLog)
            
            # Apply filters
            if website:
                query = query.where(ScraperLog.website.like(f"%{website}%"))
            if status:
                query = query.where(ScraperLog.status == status)
            
            # Order by most recent
            query = query.order_by(desc(ScraperLog.started_at))
            
            # Count total
            count_query = select(func.count()).select_from(ScraperLog)
            if website:
                count_query = count_query.where(ScraperLog.website.like(f"%{website}%"))
            if status:
                count_query = count_query.where(ScraperLog.status == status)
            
            total = await session.scalar(count_query)
            
            # Apply pagination
            query = query.offset(skip).limit(limit)
            
            # Execute
            result = await session.execute(query)
            sessions = result.scalars().all()
            
            return {
                "total": total,
                "skip": skip,
                "limit": limit,
                "sessions": [
                    {
                        "id": s.id,
                        "website": s.website,
                        "status": s.status,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                        "error_message": s.error_message,
                        "products_scraped": s.products_scraped,
                        "robots_txt_allowed": s.robots_txt_allowed,
                        "bot_protection_detected": s.bot_protection_detected
                    }
                    for s in sessions
                ]
            }
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_statistics():
    """Get database statistics."""
    try:
        async with AsyncSessionLocal() as session:
            # Total products
            total_products = await session.scalar(select(func.count()).select_from(Product))
            
            # Total shipping providers
            total_shipping = await session.scalar(select(func.count()).select_from(ShippingProvider))
            
            # Total sessions
            total_sessions = await session.scalar(select(func.count()).select_from(ScraperLog))
            
            # Successful sessions
            successful_sessions = await session.scalar(
                select(func.count()).select_from(ScraperLog).where(ScraperLog.status == "success")
            )
            
            # Products by website
            website_stats_result = await session.execute(
                select(
                    Product.source_website,
                    func.count(Product.id).label("count")
                ).group_by(Product.source_website)
            )
            website_stats = {row[0]: row[1] for row in website_stats_result.all()}
            
            # Average price
            avg_price = await session.scalar(select(func.avg(Product.price)))
            
            # Delivery type distribution
            delivery_type_result = await session.execute(
                select(
                    ShippingProvider.delivery_type,
                    func.count(ShippingProvider.id).label("count")
                ).group_by(ShippingProvider.delivery_type)
            )
            delivery_types = {row[0]: row[1] for row in delivery_type_result.all()}
            
            # Recent scraping activity (last 24 hours)
            recent_sessions = await session.scalar(
                select(func.count()).select_from(ScraperLog).where(
                    ScraperLog.started_at >= datetime.now().date()
                )
            )
            
            return {
                "total_products": total_products,
                "total_shipping_providers": total_shipping,
                "total_sessions": total_sessions,
                "successful_sessions": successful_sessions,
                "success_rate": f"{(successful_sessions / total_sessions * 100):.1f}%" if total_sessions > 0 else "0%",
                "average_product_price": float(avg_price) if avg_price else 0,
                "products_by_website": website_stats,
                "shipping_by_delivery_type": delivery_types,
                "recent_scraping_sessions_today": recent_sessions
            }
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/websites")
async def get_websites():
    """Get list of all scraped websites."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Product.source_website, func.count(Product.id).label("product_count"))
                .group_by(Product.source_website)
                .order_by(desc("product_count"))
            )
            websites = result.all()
            
            return {
                "total_websites": len(websites),
                "websites": [
                    {
                        "name": row[0],
                        "product_count": row[1]
                    }
                    for row in websites
                ]
            }
    except Exception as e:
        logger.error(f"Error fetching websites: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
