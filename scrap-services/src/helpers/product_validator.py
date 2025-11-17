"""Product page validation logic."""
from typing import Optional, Dict, List
from playwright.async_api import Page
from bs4 import BeautifulSoup
from src.config import settings
from src.constants import (
    MIN_TITLE_LENGTH,
    MIN_DESCRIPTION_LENGTH,
    MIN_PRODUCT_INDICATORS,
    MIN_PRODUCT_INDICATORS_WITH_URL_PATTERN,
)
import re


class ProductPageValidator:
    """Validates whether a page is a product page."""

    def __init__(self):
        self.currency_symbols = ["$", "€", "£", "kr", "DKK", "SEK", "NOK"]

    async def validate_product_page(
        self,
        page: Page,
        url: str
    ) -> tuple[bool, Dict[str, bool]]:
        """Validate if page is a product page.

        Args:
            page: Playwright page object
            url: Page URL

        Returns:
            Tuple of (is_valid, indicators_dict)
        """
        # Check URL patterns first
        has_product_url_pattern = self._has_product_url_pattern(url)

        # Check essential elements
        indicators = {
            'title': await self._has_valid_title(page),
            'description': await self._has_valid_description(page),
            'price': await self._has_valid_price(page),
            'add_to_cart': await self._has_add_to_cart_button(page),
        }

        # Count positive indicators
        indicator_count = sum(indicators.values())

        # Decision logic
        is_valid = (
            (indicator_count >= MIN_PRODUCT_INDICATORS) or
            (indicator_count >= MIN_PRODUCT_INDICATORS_WITH_URL_PATTERN and has_product_url_pattern)
        )

        return is_valid, indicators

    def _has_product_url_pattern(self, url: str) -> bool:
        """Check if URL has product-specific patterns.

        Args:
            url: URL to check

        Returns:
            True if has product pattern, False otherwise
        """
        url_lower = url.lower()
        pattern = r'_\d{5,}|/p/\d+|/product/|/produkt/'
        return bool(re.search(pattern, url_lower))

    async def _has_valid_title(self, page: Page) -> bool:
        """Check for valid product title.

        Args:
            page: Playwright page

        Returns:
            True if valid title found
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
                    if text and len(text.strip()) > MIN_TITLE_LENGTH:
                        return True
            except:
                continue

        return False

    async def _has_valid_description(self, page: Page) -> bool:
        """Check for valid product description.

        Args:
            page: Playwright page

        Returns:
            True if valid description found
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

                    if text and len(text.strip()) > MIN_DESCRIPTION_LENGTH:
                        return True
            except:
                continue

        return False

    async def _has_valid_price(self, page: Page) -> bool:
        """Check for valid product price.

        Args:
            page: Playwright page

        Returns:
            True if valid price found
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

        for selector in price_selectors:
            try:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    if self._contains_price(text):
                        return True
            except:
                continue

        return False

    def _contains_price(self, text: str) -> bool:
        """Check if text contains price information.

        Args:
            text: Text to check

        Returns:
            True if contains price
        """
        has_currency = any(symbol in text for symbol in self.currency_symbols)
        has_digit = any(char.isdigit() for char in text)
        return has_currency or has_digit

    async def _has_add_to_cart_button(self, page: Page) -> bool:
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
                        return True
            except:
                continue

        return False
