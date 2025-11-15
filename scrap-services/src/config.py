"""Configuration settings for the scraper application."""
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Centralizes all configuration for the scraper application including:
    - Database connection settings
    - Browser automation parameters
    - Retry and timeout configurations
    - Selector patterns for common UI elements
    - Test data for checkout flows

    All settings can be overridden via .env file.
    """

    # Database
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str

    # Database Pool
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Logging
    log_level: str = "INFO"

    # Scraper Browser Settings
    headless_mode: bool
    screenshot_enabled: bool
    scrape_delay: int

    # API Security
    api_key: str = "your-api-key-here"

    # Retry & Timeout Settings
    max_retries: int = 3
    page_timeout: int = 30000  # milliseconds
    navigation_timeout: int = 10000  # milliseconds
    element_timeout: int = 5000  # milliseconds
    cookie_dismiss_timeout: int = 3000  # milliseconds

    # Sleep/Wait Times (in seconds)
    dynamic_content_wait: float = 1.0
    page_update_wait: float = 1.0
    cart_modal_wait: float = 1.0
    variant_select_wait: float = 0.5
    checkout_step_wait: float = 1.0
    validation_retry_wait: float = 1.0

    # Checkout Settings
    max_checkout_steps: int = 5

    # Test Data for Checkout Forms
    test_email: str = "test@example.com"
    test_first_name: str = "Test"
    test_last_name: str = "User"
    test_phone: str = "71609427"
    test_address: str = "Dalen 10"
    test_postal_code: str = "2860"
    test_city: str = "Søborg"
    test_country: str = "Denmark"

    # Product Discovery
    max_discovery_attempts: int = 2
    max_validation_attempts: int = 5  # Validate more candidates for better success rate

    # Non-product URL patterns (for filtering)
    non_product_patterns: List[str] = [
        "/blog/",
        "/article/",
        "/news/",
        "/press/",
        "/category/",
        "/categories/",
        "/collection/",
        "/collections/",
        "/search/",
        "/tag/",
        "/tags/",
        "/about/",
        "/contact/",
        "/help/",
        "/support/",
        "/account/",
        "/login/",
        "/register/",
        "/signup/",
        "/cart/",
        "/basket/",
        "/checkout/",
        "/terms/",
        "/privacy/",
        "/policy/",
        "/faq/",
        "/guide/",
        "/tutorial/",
        "/store-locator/",
        "/stores/",
        "/locations/",
    ]

    # Cookie Consent Selectors (Danish + English)
    cookie_selectors: List[str] = [
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

    # Variant/Size Selectors
    variant_selectors: List[str] = [
        "table.variations select",
        ".variations select",
        "select.variation_select",
        'select[name^="attribute_"]',
        'label[for*="size"]',
        'label[for*="variant"]',
        'button[data-test*="size"]',
        "a.size-option",
        "button[data-size]",
        'button[class*="size"]',
        ".size-selector button",
        'select[data-test="select-size"]',
        'select[name*="size"]',
        'select[name*="variant"]',
        'select[name*="antal"]',
        'input[type="radio"][name*="size"]',
        'input[type="radio"][name*="variant"]',
        "[data-size]",
    ]

    # Add to Cart Button Selectors (Danish + English)
    add_to_cart_selectors: List[str] = [
        'button:has-text("Læg i kurv")',
        'a:has-text("Læg i kurv")',
        'a:has-text("Læg i indkøbskurven")',
        'button:has-text("Tilføj til kurv")',
        'a:has-text("Tilføj til kurv")',
        'button:has-text("Add to cart")',
        'a:has-text("Add to cart")',
        'button:has-text("Add to basket")',
        'a:has-text("Add to basket")',
        'button[class*="add-to-cart"]',
        'a[class*="add-to-cart"]',
        'button[class*="add-to-basket"]',
        'a[class*="add-to-basket"]',
        'button[class*="buy-button"]',
        'a[class*="buy-button"]',
        'button[id*="add-to-cart"]',
        'a[id*="add-to-cart"]',
        'button[id*="addToCart"]',
        'a[id*="addToCart"]',
        ".add-to-cart",
        "#add-to-cart-button",
        '[data-test="add-to-cart"]',
        'button:has-text("Køb")[class*="buy"]',
        'button:has-text("Køb")[class*="cart"]',
        'a:has-text("Køb")[class*="buy"]',
        'a:has-text("Køb")[class*="cart"]',
    ]

    # Cart Validation Indicator Selectors
    cart_indicator_selectors: List[str] = [
        '[class*="cart-modal"]',
        '[class*="cart-popup"]',
        '[class*="mini-cart"]',
        '[class*="MiniCart"]',
        '[id*="cart-modal"]',
        '[class*="kurv"]',
        '[class*="Kurv"]',
        "text=er tilføjet",
        "text=tilføjet til kurv",
        "text=added to cart",
        "text=tilføjet",
        '[class*="success"]',
        '[class*="notification"]',
        '[class*="cart-item"]',
        '[class*="CartItem"]',
        '[data-test*="cart"]',
        '[class*="cart-drawer"]',
        '[class*="CartDrawer"]',
        '[class*="cart-sidebar"]',
        '[class*="basket"]',
        '[class*="SessionMenu"]',
        'button:has-text("Se kurv")',
        'a:has-text("Se kurv")',
        'button:has-text("Gå til kurv")',
    ]

    # Cart Quantity Indicator Selectors
    cart_quantity_selectors: List[str] = [
        '[class*="cart-count"]',
        '[class*="cart-quantity"]',
        '[class*="basket-count"]',
        '[id*="cart-count"]',
        ".cart-badge",
        ".cart-counter",
        '[class*="cart-badge"]',
        '[class*="CartBadge"]',
        '[data-test*="cart-count"]',
    ]

    # Checkout/Cart Link Selectors
    checkout_selectors: List[str] = [
        'a:has-text("Gå til kassen")',
        'a:has-text("Til kassen")',
        'button:has-text("Gå til kassen")',
        'button:has-text("Fortsæt til kassen")',
        'button:has-text("Fortsæt")',
        'a:has-text("Se kurv")',
        'a:has-text("Checkout")',
        'a:has-text("Go to checkout")',
        'button:has-text("Checkout")',
        'a[href*="/checkout"]',
        'a[href*="/cart"]',
        'a[href*="/kurv"]',
        'a[href*="/kassen"]',
        ".checkout-button",
        "#checkout-button",
        '[data-test="checkout"]',
    ]

    # Checkout Button Selectors (on cart page)
    checkout_button_selectors: List[str] = [
        'button:has-text("Gå til kassen")',
        'button:has-text("Til kassen")',
        'button:has-text("Checkout")',
        'button:has-text("Fortsæt")',
        'button:has-text("Continue")',
        '[class*="checkout"][type="button"]',
        '[class*="proceed"][type="button"]',
    ]

    # Checkout Form Field Selectors
    combined_name_selectors: List[str] = [
        'input[name="name"]:not([name*="first"]):not([name*="last"])',
        'input[name*="navn" i]:not([name*="fornavn" i]):not([name*="efternavn" i])',
        'input[placeholder*="fornavn og efternavn" i]',
        'input[placeholder*="first and last name" i]',
        'input[id*="fullname" i]',
        'input[name*="fullname" i]',
        'input[name*="full_name" i]',
    ]

    email_selectors: List[str] = [
        'input[type="email"]',
        'input[name*="email" i]',
        'input[id*="email" i]',
        'input[placeholder*="email" i]',
        "#billing_email",
        "#email",
    ]

    first_name_selectors: List[str] = [
        'input[name*="first" i][name*="name" i]',
        'input[name*="fornavn" i]',
        'input[id*="first" i][id*="name" i]',
        'input[placeholder*="first" i]',
        'input[placeholder*="fornavn" i]',
        'input[name="firstName"]',
        'input[name="firstname"]',
        'input[id="firstName"]',
        "#billing_first_name",
    ]

    last_name_selectors: List[str] = [
        'input[name*="last" i][name*="name" i]',
        'input[name*="efternavn" i]',
        'input[id*="last" i][id*="name" i]',
        'input[placeholder*="last" i]',
        'input[placeholder*="efternavn" i]',
        'input[name="lastName"]',
        'input[name="lastname"]',
        'input[id="lastName"]',
        "#billing_last_name",
    ]

    phone_selectors: List[str] = [
        'input[type="tel"]',
        'input[name*="phone" i]',
        'input[name*="telefon" i]',
        'input[id*="phone" i]',
        'input[placeholder*="phone" i]',
        'input[placeholder*="telefon" i]',
        "#billing_phone",
    ]

    address_selectors: List[str] = [
        'input[name*="address" i]:not([name*="2"])',
        'input[name*="adresse" i]:not([name*="2"])',
        'input[id*="address" i]:not([id*="2"])',
        'input[placeholder*="address" i]',
        'input[placeholder*="adresse" i]',
        'input[placeholder*="gade" i]',
        'input[name="address"]',
        'input[name="streetAddress"]',
        'input[id="address"]',
        "#billing_address_1",
    ]

    postal_code_selectors: List[str] = [
        'input[name*="postal" i]',
        'input[name*="zip" i]',
        'input[name*="postnummer" i]',
        'input[id*="postal" i]',
        'input[placeholder*="postal" i]',
        'input[placeholder*="postnummer" i]',
        "#billing_postcode",
    ]

    city_selectors: List[str] = [
        'input[name*="city" i]',
        'input[name*="by" i]',
        'input[id*="city" i]',
        'input[placeholder*="city" i]',
        'input[placeholder*="by" i]',
        "#billing_city",
    ]

    # Next/Continue Button Selectors (for multi-step checkout)
    next_button_selectors: List[str] = [
        'button:has-text("Næste")',
        'button:has-text("Fortsæt")',
        'button:has-text("Gå til levering")',
        'button:has-text("Til betaling")',
        'a:has-text("Næste")',
        'a:has-text("Fortsæt")',
        'a:has-text("Gå til levering")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'button:has-text("Proceed")',
        'button:has-text("Go to delivery")',
        'a:has-text("Next")',
        'a:has-text("Continue")',
        'button[type="submit"]',
        'input[type="submit"]',
        'button[class*="continue"]',
        'button[class*="next"]',
        'button[class*="proceed"]',
        'a[class*="continue"]',
        'a[class*="next"]',
    ]

    # Delivery Type Classification Keywords
    home_delivery_keywords: List[str] = [
        "hjemmelevering",
        "hjemlevering",
        "home delivery",
        "levering til døren",
        "delivery to door",
        "door delivery",
        "hjemme",
        "til døren",
        "leveres hjem",
        "burd",
        "courier",
    ]

    parcel_shop_keywords: List[str] = [
        "pakkeshop",
        "parcel shop",
        "afhentning",
        "pakkeboks",
        "pickup",
        "collect",
        "afhentn",
        "pakkehop",
        "shop",
    ]

    store_pickup_keywords: List[str] = [
        "butik",
        "store",
        "afhent i butik",
        "collect in store",
        "click and collect",
        "hent i butik",
        "butikken",
        "matas butik",
    ]

    parcel_locker_keywords: List[str] = [
        "pakkeboks",
        "parcel locker",
        "locker",
        "automat",
        "boks",
        "swipbox",
        "pakkebox",
    ]

    # Shipping Price Patterns (regex)
    shipping_price_patterns: List[str] = [
        r"\d+\s*kr",
        r"kr\s*\d+",
        r"\d+\s*DKK",
        r"gratis",
        r"free",
    ]

    # Expand/Show More Button Selectors (for shipping sections)
    expand_selectors: List[str] = [
        'button:has-text("Vis mere")',
        'button:has-text("Se flere")',
        'button:has-text("Udvid")',
        'button:has-text("Show more")',
        'button:has-text("Expand")',
        'button:has-text("View more")',
        "summary",
        'button[aria-expanded="false"]',
    ]

    # Non-Product URL Patterns
    non_product_patterns: List[str] = [
        "/blog/",
        "/article/",
        "/news/",
        "/story/",
        "/stories/",
        "/category/",
        "/categories/",
        "/collection/",
        "/collections/",
        "/guide/",
        "/guides/",
        "/tips/",
        "/advice/",
        "/campaign/",
        "/campaigns/",
        "/promotion/",
        "/promotions/",
        "/inspiration/",
        "/editorial/",
        "/magazine/",
    ]

    # Default Values
    default_currency: str = "USD"
    default_availability: str = "in stock"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env


settings = Settings()
