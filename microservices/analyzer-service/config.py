"""Configuration settings for Analyzer Service."""
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
    
    # Playwright settings
    page_timeout = int(os.getenv('PAGE_TIMEOUT', '30000'))
    headless_mode = os.getenv('HEADLESS_MODE', 'True').lower() not in ('false', '0', 'no', 'off')
    
    # Analysis patterns
    non_product_patterns = [
        r'/cart', r'/checkout', r'/account', r'/login', r'/register',
        r'/search', r'/category', r'/categories', r'/collections',
        r'/about', r'/contact', r'/help', r'/faq', r'/terms',
        r'/privacy', r'/shipping', r'/returns', r'/blog', r'/news'
    ]
    
    # Add to cart button selectors
    add_to_cart_selectors = [
        'button[name*="add"]',
        'button[id*="add"]',
        'button[class*="add"]',
        'button:has-text("Add to cart")',
        'button:has-text("Add to bag")',
        'button:has-text("Add to basket")',
        'button:has-text("Buy now")',
        'input[value*="Add"]',
        '[data-action*="add"]',
        '.add-to-cart',
        '#add-to-cart',
        '.addtocart',
        '#addToCart',
    ]
    
    # Cookie Consent Selectors (Danish + English)
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
        'button[id*="accept"]',
        'button[id*="cookie"]',
        'button[class*="accept"]',
        'button[class*="cookie"]',
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        ".cookie-accept",
        ".accept-cookies",
        ".coi-accept-all",
        '[data-test*="cookie"][data-test*="accept"]',
    ]


settings = Settings()
