"""Scraper service helper functions to reduce complexity."""
from typing import List, Optional, Dict
from playwright.async_api import Page
from src.schemas.messages import ShippingProvider
import logging

logger = logging.getLogger(__name__)


class ShippingTextParser:
    """Parses shipping information from text."""

    def __init__(self):
        self.currency_symbols = ["kr", "DKK", "SEK", "NOK", "$", "€", "£"]
        self.provider_keywords = {
            "postnord": "PostNord",
            "gls": "GLS",
            "budbee": "Budbee",
            "dao": "DAO",
            "bring": "Bring",
            "dhl": "DHL",
            "ups": "UPS",
            "fedex": "FedEx",
        }

    def parse_shipping_text(self, text: str) -> Optional[ShippingProvider]:
        """Parse shipping provider from text.

        Args:
            text: Text containing shipping information

        Returns:
            ShippingProvider or None
        """
        if not text or len(text) < 10:
            return None

        text_lower = text.lower()

        # Extract components
        name = self._extract_provider_name(text, text_lower)
        if not name:
            return None

        price, currency = self._extract_shipping_cost(text, text_lower)
        delivery_time = self._extract_delivery_time(text_lower)
        delivery_type = self._classify_delivery_type(text_lower)

        return ShippingProvider(
            name=name,
            price=price,
            currency=currency or "DKK",
            delivery_time=delivery_time,
            delivery_type=delivery_type,
            description=text[:200] if len(text) > 200 else text
        )

    def _extract_provider_name(self, text: str, text_lower: str) -> Optional[str]:
        """Extract provider name from text.

        Args:
            text: Original text
            text_lower: Lowercased text

        Returns:
            Provider name or None
        """
        # Check for known providers
        for keyword, name in self.provider_keywords.items():
            if keyword in text_lower:
                return name

        # Fallback: extract first few words
        words = text.split()
        if words:
            return " ".join(words[:3])

        return None

    def _extract_shipping_cost(
        self,
        text: str,
        text_lower: str
    ) -> tuple[Optional[float], Optional[str]]:
        """Extract shipping cost and currency.

        Args:
            text: Text to parse
            text_lower: Lowercased text

        Returns:
            Tuple of (price, currency)
        """
        import re

        # Check for free shipping
        if any(word in text_lower for word in ["gratis", "free", "fri fragt"]):
            return 0.0, "DKK"

        # Extract price patterns
        patterns = [
            r"(\d+(?:,\d+)?)\s*kr",
            r"kr\s*(\d+(?:,\d+)?)",
            r"(\d+(?:,\d+)?)\s*DKK",
            r"DKK\s*(\d+(?:,\d+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(",", ".")
                try:
                    return float(price_str), "DKK"
                except ValueError:
                    continue

        return None, None

    def _extract_delivery_time(self, text_lower: str) -> Optional[str]:
        """Extract delivery time from text.

        Args:
            text_lower: Lowercased text

        Returns:
            Delivery time string or None
        """
        import re

        time_patterns = [
            r"(\d+-\d+\s+(?:dage|days|hverdage|arbejdsdage))",
            r"(\d+\s+(?:dage|days|hverdage|arbejdsdage))",
            r"(i\s+morgen|tomorrow|næste\s+dag|next\s+day)",
        ]

        for pattern in time_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return match.group(1)

        return None

    def _classify_delivery_type(self, text_lower: str) -> str:
        """Classify delivery type from text.

        Args:
            text_lower: Lowercased text

        Returns:
            Delivery type classification
        """
        from src.config import settings

        if any(kw in text_lower for kw in settings.home_delivery_keywords):
            return "home_delivery"
        elif any(kw in text_lower for kw in settings.parcel_shop_keywords):
            return "parcel_shop"
        elif any(kw in text_lower for kw in settings.store_pickup_keywords):
            return "store_pickup"
        elif any(kw in text_lower for kw in settings.parcel_locker_keywords):
            return "parcel_locker"
        else:
            return "other"


class ShippingExtractorHelper:
    """Helper for extracting shipping options from JavaScript."""

    @staticmethod
    def build_shipping_extraction_script() -> str:
        """Build JavaScript for extracting shipping options.

        Returns:
            JavaScript code as string
        """
        return """() => {
            const results = [];
            const shippingKeywords = /levering|fragt|shipping|delivery|postnord|gls|budbee|dao|burd|afhent|pakkeshop|hjemlevering|erhverv|palle|ekspres|express/i;
            const pricePattern = /(?:fra\\s+)?\\d+\\s*kr/i;

            // Strategy 1: Find list items
            const listItems = document.querySelectorAll('li, [role="option"], [role="radio"]');
            const seen = new Set();

            listItems.forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return;
                }

                const text = (el.innerText || el.textContent || '').trim();

                if (text.length >= 10 && text.length <= 500) {
                    const hasShipping = shippingKeywords.test(text);
                    const hasPrice = pricePattern.test(text);

                    if (hasShipping && hasPrice) {
                        const lines = text.split('\\n').filter(l => l.trim());
                        const coreText = lines.slice(0, 5).join(' ').trim();

                        if (coreText.length >= 10 && !seen.has(coreText)) {
                            seen.add(coreText);
                            results.push({
                                text: coreText,
                                tag: el.tagName,
                                className: el.className || ''
                            });
                        }
                    }
                }
            });

            // Strategy 2: Find shipping containers
            const shippingContainers = document.querySelectorAll(
                '[class*="shipping"], [class*="delivery"], [class*="levering"], ' +
                '[class*="option"], [class*="method"], [id*="shipping"], [id*="delivery"]'
            );

            shippingContainers.forEach(container => {
                const style = window.getComputedStyle(container);
                if (style.display === 'none' || style.visibility === 'hidden') {
                    return;
                }

                Array.from(container.children).forEach(child => {
                    const childStyle = window.getComputedStyle(child);
                    if (childStyle.display === 'none' || childStyle.visibility === 'hidden') {
                        return;
                    }

                    const text = (child.innerText || child.textContent || '').trim();

                    if (text.length >= 15 && text.length <= 400) {
                        if (shippingKeywords.test(text) && pricePattern.test(text)) {
                            if (!seen.has(text)) {
                                seen.add(text);
                                results.push({
                                    text: text,
                                    tag: child.tagName,
                                    className: child.className || ''
                                });
                            }
                        }
                    }
                });
            });

            return results;
        }"""

    @staticmethod
    def deduplicate_providers(providers: List[ShippingProvider]) -> List[ShippingProvider]:
        """Deduplicate shipping providers by name and price.

        Args:
            providers: List of providers

        Returns:
            Deduplicated list
        """
        seen = set()
        unique_providers = []

        for provider in providers:
            key = (provider.name.lower(), provider.price, provider.currency)
            if key not in seen:
                seen.add(key)
                unique_providers.append(provider)

        return unique_providers
