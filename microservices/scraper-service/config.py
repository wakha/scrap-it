"""Configuration settings for Scraper Service."""
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
    
    # Test customer data for checkout
    test_email = os.getenv('TEST_EMAIL', 'test@example.com')
    test_first_name = os.getenv('TEST_FIRST_NAME', 'John')
    test_last_name = os.getenv('TEST_LAST_NAME', 'Doe')
    test_phone = os.getenv('TEST_PHONE', '71609427')
    test_address = os.getenv('TEST_ADDRESS', 'Dalen 10')
    test_postal_code = os.getenv('TEST_POSTAL_CODE', '2860')
    test_city = os.getenv('TEST_CITY', 'Søborg')
    
    # Cookie consent selectors (Danish + English)
    cookie_selectors = [
        'button:has-text("Acceptér alle")',
        'button:has-text("Accepter alle")',
        'button:has-text("Accept alle")',
        'button:has-text("Godkend alle")',
        'button:has-text("Accept all")',
        'button:has-text("Accept")',
        'button:has-text("Accepter")',
        'button:has-text("Godkend")',
        'button:has-text("NØDVENDIGE")',
        'button:has-text("OK")',
        'button:has-text("I agree")',
        'button[id*="accept"]',
        'button[id*="cookie"]',
        'button[class*="accept"]',
        'button[class*="cookie"]',
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        ".cookie-accept",
        ".accept-cookies",
        ".coi-accept-all",
        '[data-test*="cookie"][data-test*="accept"]',
        '#cookie-accept',
        '[data-cookie-accept]',
    ]


settings = Settings()
