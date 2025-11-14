"""Database connection test for CI/CD pipeline."""
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from src.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_database_connection():
    """
    Test that the application can connect to the MySQL database.
    
    This test validates:
    1. Database connection string is correct
    2. Credentials are valid
    3. Database service is accessible
    4. Basic query execution works
    """
    # Build connection string
    database_url = (
        f"mysql+aiomysql://{settings.db_user}:{settings.db_password}@"
        f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )
    
    # Create engine
    engine = create_async_engine(database_url, echo=False)
    
    try:
        # Create session
        async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session_maker() as session:
            # Execute simple query to verify connection
            result = await session.execute(text("SELECT 1 as connection_test"))
            row = result.fetchone()
            
            # Assert connection works
            assert row is not None, "Database query returned no result"
            assert row[0] == 1, f"Expected 1, got {row[0]}"
            
        print("✅ Database connection successful")
        
    finally:
        # Clean up
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_tables_exist():
    """
    Test that required database tables exist.
    
    This ensures the database schema has been initialized correctly.
    """
    database_url = (
        f"mysql+aiomysql://{settings.db_user}:{settings.db_password}@"
        f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )
    
    engine = create_async_engine(database_url, echo=False)
    
    try:
        async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session_maker() as session:
            # Check if main tables exist
            result = await session.execute(text("""
                SELECT COUNT(*) as table_count 
                FROM information_schema.tables 
                WHERE table_schema = :db_name 
                AND table_name IN ('shipping_providers', 'products', 'scraper_logs')
            """), {"db_name": settings.db_name})
            
            row = result.fetchone()
            table_count = row[0]
            
            # We expect at least the core tables
            assert table_count >= 3, f"Expected at least 3 tables, found {table_count}"
            
        print(f"✅ Database schema validated ({table_count} tables found)")
        
    finally:
        await engine.dispose()
