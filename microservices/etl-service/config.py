"""Configuration settings for ETL Service."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env files only when running locally (not in Docker)
# Docker gets env vars directly from docker-compose.yml
if not os.getenv('RUNNING_IN_DOCKER'):
    env_path = Path(__file__).parent.parent / '.env'
    env_local_path = Path(__file__).parent.parent / '.env.local'
    
    # Load .env.local first (local dev), fallback to .env (Docker settings)
    if env_local_path.exists():
        load_dotenv(dotenv_path=env_local_path, override=True)
    elif env_path.exists():
        load_dotenv(dotenv_path=env_path)


class Settings:
    """Configuration settings."""
    
    # Database settings
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', '3306'))
    db_user = os.getenv('DB_USER', 'scraper')
    db_password = os.getenv('DB_PASSWORD', 'scraper123')
    db_name = os.getenv('DB_NAME', 'scraper_db')
    db_pool_size = int(os.getenv('DB_POOL_SIZE', '10'))
    db_max_overflow = int(os.getenv('DB_MAX_OVERFLOW', '20'))
    
    # Retry settings
    max_retries = int(os.getenv('MAX_RETRIES', '3'))


settings = Settings()
