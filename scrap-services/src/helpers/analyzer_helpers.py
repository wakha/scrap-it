"""Analyzer helper functions to reduce complexity."""
from typing import Optional, Dict, List
from playwright.async_api import Page
from src.config import settings
import logging

logger = logging.getLogger(__name__)


class URLValidator:
    """Validates URLs and checks patterns."""
    
    @staticmethod
    def is_homepage(url: str) -> bool:
        """Check if URL is a homepage.
        
        Args:
            url: URL to check
            
        Returns:
            True if homepage, False otherwise
        """
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        return not path or path == '' or len(path.split('/')) == 0
    
    @staticmethod
    def has_non_product_pattern(url: str) -> bool:
        """Check if URL contains non-product patterns.
        
        Args:
            url: URL to check
            
        Returns:
            True if contains non-product pattern
        """
        url_lower = url.lower()
        for pattern in settings.non_product_patterns:
            if pattern in url_lower:
                logger.debug(f"[PRODUCT] URL contains non-product pattern: {pattern}")
                return True
        return False
    
    @staticmethod
    def has_product_url_pattern(url: str) -> bool:
        """Check if URL has product-specific patterns.
        
        Args:
            url: URL to check
            
        Returns:
            True if has product pattern
        """
        import re
        url_lower = url.lower()
        return bool(re.search(r'_\d{5,}|/p/\d+|/product/|/produkt/', url_lower))


class ElementChecker:
    """Checks for specific page elements."""
    
    @staticmethod
    async def has_title(page: Page) -> bool:
        """Check for product title.
        
        Args:
            page: Playwright page
            
        Returns:
            True if title found
        """
        title_selectors = [
            'h1',
            '[itemprop="name"]',
            '[class*="product"][class*="title"]',
            '[class*="product"][class*="name"]',
            '[data-testid*="title"]',
            '[data-testid*="name"]',
            '[data-test*="product-title"]',
        ]
        
        for selector in title_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if text and len(text.strip()) > 5:
                        logger.debug(f"[PRODUCT] ✓ Found title: {text.strip()[:50]}")
                        return True
            except:
                continue
        return False
    
    @staticmethod
    async def has_description(page: Page) -> bool:
        """Check for product description.
        
        Args:
            page: Playwright page
            
        Returns:
            True if description found
        """
        description_selectors = [
            '[itemprop="description"]',
            '[class*="description"]',
            '[class*="product-detail"]',
            '[class*="product-info"]',
            '[data-testid*="description"]',
            '[data-test*="description"]',
            'meta[name="description"]',
            'meta[property="og:description"]',
        ]
        
        for selector in description_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    if selector.startswith('meta'):
                        text = await elem.get_attribute('content')
                    else:
                        text = await elem.inner_text()
                    
                    if text and len(text.strip()) > 10:
                        logger.debug("[PRODUCT] ✓ Found description")
                        return True
            except:
                continue
        return False
    
    @staticmethod
    async def has_price(page: Page) -> bool:
        """Check for product price.
        
        Args:
            page: Playwright page
            
        Returns:
            True if price found
        """
        # Try structured data first
        try:
            structured_price = await page.evaluate("""() => {
                const priceEl = document.querySelector('[itemprop="price"]');
                if (priceEl) {
                    const content = priceEl.getAttribute('content') || priceEl.innerText;
                    return content;
                }
                return null;
            }""")
            if structured_price:
                logger.debug(f"[PRODUCT] ✓ Found structured price: {structured_price}")
                return True
        except:
            pass
        
        # Try class-based selectors
        price_selectors = [
            '[class*="price"]:not([class*="old"]):not([class*="original"])',
            '[data-testid*="price"]',
            '[data-test*="price"]',
            'span[class*="Price"]',
            '[class*="product-price"]',
        ]
        
        currency_symbols = ["$", "€", "£", "kr", "DKK", "SEK", "NOK"]
        
        for selector in price_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    has_currency = any(symbol in text for symbol in currency_symbols)
                    has_digit = any(char.isdigit() for char in text)
                    
                    if has_currency or has_digit:
                        logger.debug(f"[PRODUCT] ✓ Found price: {text.strip()[:30]}")
                        return True
            except:
                continue
        return False
    
    @staticmethod
    async def has_add_to_cart(page: Page) -> bool:
        """Check for add to cart button.
        
        Args:
            page: Playwright page
            
        Returns:
            True if button found and visible
        """
        for selector in settings.add_to_cart_selectors[:25]:
            try:
                button = await page.query_selector(selector)
                if button:
                    is_visible = await button.is_visible()
                    if is_visible:
                        logger.debug("[PRODUCT] ✓ Found add-to-cart button")
                        return True
            except:
                continue
        return False


class ProductPageDecider:
    """Decides if a page is a product page based on indicators."""
    
    @staticmethod
    def is_product_page(
        indicators: Dict[str, bool],
        has_product_url_pattern: bool
    ) -> bool:
        """Decide if page is a product page.
        
        Args:
            indicators: Dict of element indicators found
            has_product_url_pattern: Whether URL has product pattern
            
        Returns:
            True if product page
        """
        indicator_count = sum(indicators.values())
        
        # Need at least 3 out of 4 indicators, OR 2 indicators + product URL pattern
        is_product = (
            (indicator_count >= 3) or 
            (indicator_count >= 2 and has_product_url_pattern)
        )
        
        if is_product:
            logger.info(
                f"[PRODUCT] [OK] Valid product page ({indicator_count}/4 indicators, "
                f"URL pattern: {has_product_url_pattern}) - "
                f"title: {indicators.get('title', False)}, "
                f"desc: {indicators.get('description', False)}, "
                f"price: {indicators.get('price', False)}, "
                f"cart: {indicators.get('add_to_cart', False)}"
            )
        else:
            missing = [k for k, v in indicators.items() if not v]
            logger.debug(
                f"[PRODUCT] ✗ Not a valid product page ({indicator_count}/4 indicators, "
                f"URL pattern: {has_product_url_pattern}) - Missing: {missing}"
            )
        
        return is_product
