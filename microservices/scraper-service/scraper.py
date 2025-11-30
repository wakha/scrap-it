"""
Intelligent Product Scraper Service
A universal scraper that adapts to different website structures and checkout flows.
"""
import logging
import asyncio
import traceback
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
import sys
import os

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.schemas import AnalysisResult, ScrapedProduct, ShippingProvider
from utils.extractors import DataExtractor
from config import settings

logger = logging.getLogger(__name__)


class CheckoutPathDiscovery:
    """Discovers checkout paths on different websites."""

    @staticmethod
    async def discover_checkout_urls(page: Page, base_url: str) -> List[str]:
        """
        Discover possible checkout URLs by analyzing the website structure.

        Args:
            page: Playwright page object
            base_url: Base URL of the website

        Returns:
            List of potential checkout URLs
        """
        logger.info("[DISCOVERY] Discovering checkout paths...")

        checkout_urls = []

        # Strategy 1: Domain-specific checkout paths (highest priority)
        domain = urlparse(base_url).netloc.lower()
        domain_specific_paths = {
            "matas.dk": ["/levering"],
            "www.matas.dk": ["/levering"],
            "jollyroom.dk": ["/kassen"],
            "www.jollyroom.dk": ["/kassen"],
        }

        # Check if we have domain-specific paths
        for site_domain, paths in domain_specific_paths.items():
            if site_domain in domain:
                logger.info(f"[DISCOVERY] Using domain-specific paths for {site_domain}")
                for path in paths:
                    checkout_urls.append(urljoin(base_url, path))
                # Return early with domain-specific paths (don't dilute with generic ones)
                return checkout_urls

        # Strategy 2: Common checkout path patterns (fallback for unknown sites)
        common_paths = [
            "/checkout",
            "/checkout/",
            "/kassen",
            "/kassen/",
            "/levering",
            "/levering/",
            "/cart/checkout",
            "/basket/checkout",
            "/kurv/checkout",
            "/checkout/delivery",
            "/checkout/shipping",
        ]

        for path in common_paths:
            checkout_urls.append(urljoin(base_url, path))

        # Strategy 3: Analyze links on current page
        try:
            links = await page.evaluate("""() => {
                const checkoutKeywords = ['checkout', 'kassen', 'levering', 'delivery', 'shipping', 'til kassen'];
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links
                    .filter(link => {
                        const href = (link.href || '').toLowerCase();
                        const text = (link.textContent || '').toLowerCase();
                        return checkoutKeywords.some(kw => href.includes(kw) || text.includes(kw));
                    })
                    .map(link => link.href)
                    .filter((href, index, self) => self.indexOf(href) === index);
            }""")

            if links:
                logger.info(f"[DISCOVERY] Found {len(links)} checkout links on page")
                checkout_urls.extend(links)
        except Exception as e:
            logger.debug(f"[DISCOVERY] Error analyzing page links: {e}")

        # Strategy 4: Check for data attributes or API endpoints
        try:
            api_urls = await page.evaluate("""() => {
                const elements = document.querySelectorAll('[data-checkout-url], [data-shipping-url]');
                return Array.from(elements).map(el =>
                    el.getAttribute('data-checkout-url') || el.getAttribute('data-shipping-url')
                ).filter(url => url);
            }""")

            if api_urls:
                checkout_urls.extend([urljoin(base_url, url) for url in api_urls])
        except Exception:
            pass

        # Deduplicate and return
        unique_urls = list(dict.fromkeys(checkout_urls))
        logger.info(f"[DISCOVERY] Discovered {len(unique_urls)} potential checkout URLs")

        return unique_urls


class ProductExtractor:
    """Extracts product information from product pages."""

    def __init__(self):
        self.data_extractor = DataExtractor()

    async def extract_product_info(self, page: Page, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """
        Extract product information using multiple intelligent strategies.

        Args:
            page: Playwright page object
            soup: BeautifulSoup parsed HTML
            url: Product URL

        Returns:
            Dictionary with product information
        """
        logger.info("[PRODUCT] Extracting product information...")

        product_info = {
            "title": await self._extract_title(soup, page),
            "price": None,
            "currency": None,
            "description": await self._extract_description(soup),
            "image": await self._extract_image(soup),
            "url": url,
        }

        # Extract price
        price, currency = await self._extract_price(soup, page)
        product_info["price"] = price
        product_info["currency"] = currency

        logger.info(f"[PRODUCT] Extracted: {product_info['title']}, {price} {currency}")

        return product_info

    async def _extract_title(self, soup: BeautifulSoup, page: Page) -> Optional[str]:
        """Extract product title using multiple strategies."""
        try:
            # Strategy 1: Schema.org structured data
            title = self._extract_from_json_ld(soup, "name")
            if title:
                logger.info("[PRODUCT] Title from Schema.org JSON-LD")
                return title

            # Strategy 2: Open Graph
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                logger.info("[PRODUCT] Title from og:title")
                return og_title.get("content")

            # Strategy 3: H1 tag
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
                if title and len(title) > 3:
                    logger.info("[PRODUCT] Title from h1")
                    return title

            # Strategy 4: itemprop name
            itemprop_name = soup.find(attrs={"itemprop": "name"})
            if itemprop_name:
                title = itemprop_name.get_text(strip=True)
                if title:
                    logger.info("[PRODUCT] Title from itemprop")
                    return title

            # Strategy 5: Product title class patterns
            title_elem = soup.find(class_=re.compile(r"product.*title|title.*product", re.I))
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    logger.info("[PRODUCT] Title from class pattern")
                    return title

            # Strategy 6: Page title as fallback
            page_title = soup.find("title")
            if page_title:
                logger.warning("[PRODUCT] Using page title as fallback")
                return page_title.get_text(strip=True)

            return None
        except Exception as e:
            logger.error(f"[PRODUCT] Error extracting title: {e}")
            return None

    async def _extract_price(self, soup: BeautifulSoup, page: Page) -> Tuple[Optional[float], Optional[str]]:
        """Extract product price using multiple strategies."""
        try:
            # Strategy 1: Schema.org JSON-LD
            price_data = self._extract_price_from_json_ld(soup)
            if price_data:
                logger.info("[PRODUCT] Price from Schema.org JSON-LD")
                return price_data

            # Strategy 2: Open Graph price
            og_price = soup.find("meta", property="og:price:amount")
            if og_price and og_price.get("content"):
                try:
                    price = float(og_price.get("content"))
                    og_currency = soup.find("meta", property="og:price:currency")
                    currency = og_currency.get("content") if og_currency else "USD"
                    logger.info("[PRODUCT] Price from og:price")
                    return price, currency
                except (ValueError, AttributeError):
                    pass

            # Strategy 3: itemprop price
            itemprop_price = soup.find(attrs={"itemprop": "price"})
            if itemprop_price:
                price_text = itemprop_price.get_text(strip=True) or itemprop_price.get("content", "")
                if price_text:
                    price_tuple = self.data_extractor.extract_price_with_regex(price_text)
                    if price_tuple:
                        logger.info("[PRODUCT] Price from itemprop")
                        return price_tuple

            # Strategy 4: Common price class patterns
            price_patterns = [
                r"price(?!.*old|.*was|.*original)",
                r"product.*price",
                r"current.*price",
                r"sale.*price",
            ]

            for pattern in price_patterns:
                price_elem = soup.find(class_=re.compile(pattern, re.I))
                if price_elem:
                    # Skip if it's marked as old/crossed-out price
                    parent = price_elem.find_parent(["del", "s"])
                    if parent:
                        continue

                    price_text = price_elem.get_text(strip=True)
                    price_tuple = self.data_extractor.extract_price_with_regex(price_text)
                    if price_tuple:
                        logger.info(f"[PRODUCT] Price from class pattern: {pattern}")
                        return price_tuple

            # Strategy 5: Search all text for price patterns
            all_text = soup.get_text()
            price_tuple = self.data_extractor.extract_price_with_regex(all_text)
            if price_tuple:
                logger.warning("[PRODUCT] Price from text search (low confidence)")
                return price_tuple

            logger.warning("[PRODUCT] Could not extract price")
            return None, None
        except Exception as e:
            logger.error(f"[PRODUCT] Error extracting price: {e}")
            return None, None

    def _extract_from_json_ld(self, soup: BeautifulSoup, field: str) -> Optional[str]:
        """Extract field from Schema.org JSON-LD."""
        try:
            import json
            scripts = soup.find_all("script", type="application/ld+json")

            for script in scripts:
                try:
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]

                    for item in items:
                        if item.get("@type") in ["Product", "ProductModel"]:
                            value = item.get(field)
                            if value:
                                return str(value)
                except (json.JSONDecodeError, AttributeError):
                    continue

            return None
        except Exception:
            return None

    def _extract_price_from_json_ld(self, soup: BeautifulSoup) -> Optional[Tuple[float, str]]:
        """Extract price from Schema.org JSON-LD."""
        try:
            import json
            scripts = soup.find_all("script", type="application/ld+json")

            for script in scripts:
                try:
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]

                    for item in items:
                        if item.get("@type") in ["Product", "ProductModel"]:
                            offers = item.get("offers")
                            if offers:
                                offer_list = offers if isinstance(offers, list) else [offers]

                                for offer in offer_list:
                                    price_str = offer.get("price")
                                    currency = offer.get("priceCurrency", "USD")

                                    if price_str:
                                        try:
                                            price = float(price_str)
                                            return price, currency
                                        except (ValueError, TypeError):
                                            continue
                except (json.JSONDecodeError, AttributeError):
                    continue

            return None
        except Exception:
            return None

    async def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product description."""
        try:
            # Try meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                return meta_desc.get("content")

            # Try og:description
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                return og_desc.get("content")

            # Try description class
            desc_elem = soup.find(class_=re.compile(r"description|desc", re.I))
            if desc_elem:
                return desc_elem.get_text(strip=True)[:500]

            return None
        except Exception:
            return None

    async def _extract_image(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product image URL."""
        try:
            # Try og:image
            og_image = soup.find("meta", property="og:image")
            if og_image and og_image.get("content"):
                return og_image.get("content")

            # Try itemprop image
            itemprop_img = soup.find(attrs={"itemprop": "image"})
            if itemprop_img:
                return itemprop_img.get("src") or itemprop_img.get("content")

            # Try first large image
            images = soup.find_all("img")
            for img in images:
                src = img.get("src")
                if src and "product" in src.lower():
                    return src

            return None
        except Exception:
            return None


class ShippingExtractor:
    """Intelligently extracts shipping information from various UI patterns."""

    def __init__(self):
        self.data_extractor = DataExtractor()

    async def extract_shipping_info(
        self,
        page: Page,
        soup: BeautifulSoup,
        context: str = "product_page"
    ) -> List[ShippingProvider]:
        """
        Extract shipping information using intelligent pattern recognition.

        Args:
            page: Playwright page object
            soup: BeautifulSoup parsed HTML
            context: Where we're extracting from ('product_page', 'checkout', 'cart')

        Returns:
            List of ShippingProvider objects
        """
        logger.info(f"[SHIPPING] Extracting shipping from {context}...")

        providers = []

        # PRIORITY 1: Use JavaScript to extract from live page (for dynamic content)
        result = await self._extract_from_live_page(page)
        logger.info(f"[SHIPPING DEBUG] Live page (JS): {len(result)} providers")
        for p in result:
            logger.info(f"[SHIPPING DEBUG]   - {p.name}: {p.price} {p.currency} ({p.delivery_time})")
        providers.extend(result)

        # PRIORITY 2: Try multiple extraction strategies with detailed logging
        result = await self._extract_from_structured_data(soup)
        logger.info(f"[SHIPPING DEBUG] Structured data: {len(result)} providers")
        providers.extend(result)

        result = await self._extract_from_shipping_sections(soup)
        logger.info(f"[SHIPPING DEBUG] Shipping sections: {len(result)} providers")
        providers.extend(result)

        result = await self._extract_from_radio_buttons(soup)
        logger.info(f"[SHIPPING DEBUG] Radio buttons: {len(result)} providers")
        providers.extend(result)

        result = await self._extract_from_tables(soup)
        logger.info(f"[SHIPPING DEBUG] Tables: {len(result)} providers")
        providers.extend(result)

        result = await self._extract_from_cards(soup, page)
        logger.info(f"[SHIPPING DEBUG] Cards: {len(result)} providers")
        providers.extend(result)

        result = await self._extract_from_text_blocks(soup)
        logger.info(f"[SHIPPING DEBUG] Text blocks: {len(result)} providers")
        providers.extend(result)

        # Deduplicate
        unique_providers = self._deduplicate_providers(providers)

        logger.info(f"[SHIPPING] Extracted {len(unique_providers)} unique shipping options")

        return unique_providers

    async def _extract_from_live_page(self, page: Page) -> List[ShippingProvider]:
        """Extract shipping options from live page using JavaScript (handles dynamic content)."""
        providers = []

        try:
            logger.info("[SHIPPING] Querying live page for shipping options...")

            # JavaScript to find ALL visible text elements containing shipping/delivery keywords
            shipping_options = await page.evaluate("""() => {
                const results = [];
                const shippingKeywords = /levering|fragt|shipping|delivery|postnord|gls|budbee|dao|burd|afhent|pakkeshop|hjemlevering|erhverv|palle|ekspres|express/i;
                const pricePattern = /(?:fra\\s+)?\\d+\\s*kr/i;  // Matches 'Fra 39 kr' or '39 kr'

                // Strategy 1: Find list items (most common for shipping options)
                const listItems = document.querySelectorAll('li, [role="option"], [role="radio"]');
                const seen = new Set();

                listItems.forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                        return;
                    }

                    // Get text from this element and immediate children only
                    let text = '';

                    // Try innerText first (respects CSS visibility)
                    if (el.innerText) {
                        text = el.innerText.trim();
                    } else {
                        // Fallback to textContent
                        text = el.textContent.trim();
                    }

                    // Check length and keywords
                    if (text.length >= 10 && text.length <= 500) {
                        const hasShipping = shippingKeywords.test(text);
                        const hasPrice = pricePattern.test(text);

                        if (hasShipping && hasPrice) {
                            // Extract just the core shipping info (exclude nested content)
                            const lines = text.split('\\n').filter(l => l.trim());
                            const coreText = lines.slice(0, 5).join(' ').trim();  // First 5 lines only

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

                // Strategy 2: Find divs/sections with shipping classes
                const shippingContainers = document.querySelectorAll(
                    '[class*="shipping"], [class*="delivery"], [class*="levering"], ' +
                    '[class*="option"], [class*="method"], [id*="shipping"], [id*="delivery"]'
                );

                shippingContainers.forEach(container => {
                    const style = window.getComputedStyle(container);
                    if (style.display === 'none' || style.visibility === 'hidden') {
                        return;
                    }

                    // Look for direct children that might be individual options
                    const children = Array.from(container.children);

                    children.forEach(child => {
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

                // Strategy 3: Look for labels associated with radio/checkboxes
                const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
                inputs.forEach(input => {
                    const label = input.closest('label') || document.querySelector(`label[for="${input.id}"]`);
                    if (label) {
                        const text = (label.innerText || label.textContent || '').trim();
                        if (text.length >= 15 && text.length <= 400) {
                            if (shippingKeywords.test(text) || pricePattern.test(text)) {
                                if (!seen.has(text)) {
                                    seen.add(text);
                                    results.push({
                                        text: text,
                                        tag: 'LABEL',
                                        className: label.className || ''
                                    });
                                }
                            }
                        }
                    }
                });

                return results;
            }""")

            logger.info(f"[SHIPPING] Found {len(shipping_options)} shipping option elements on live page")

            # Log what was found for debugging
            for option in shipping_options[:10]:  # Log first 10
                logger.info(f"[SHIPPING DEBUG] Element ({option.get('tag')}): {option.get('text')[:100]}")

            # Parse each option
            for option in shipping_options:
                text = option.get("text", "")
                if text:
                    provider = self._parse_shipping_text(text)
                    if provider:
                        logger.info(f"[SHIPPING] Parsed from live page: {provider.name} - {provider.price} {provider.currency}")
                        providers.append(provider)

        except Exception as e:
            logger.warning(f"[SHIPPING] Error extracting from live page: {e}")

        if providers:
            logger.info(f"[SHIPPING] Found {len(providers)} from live page JavaScript")

        return providers

    async def _extract_from_structured_data(self, soup: BeautifulSoup) -> List[ShippingProvider]:
        """Extract from Schema.org or other structured data."""
        providers = []

        try:
            import json
            scripts = soup.find_all("script", type="application/ld+json")

            for script in scripts:
                try:
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]

                    for item in items:
                        if item.get("@type") in ["Product", "ProductModel"]:
                            offers = item.get("offers", {})
                            shipping_details = offers.get("shippingDetails", [])

                            if isinstance(shipping_details, list):
                                for detail in shipping_details:
                                    provider = self._parse_shipping_detail(detail)
                                    if provider:
                                        providers.append(provider)
                except (json.JSONDecodeError, AttributeError):
                    continue
        except Exception as e:
            logger.debug(f"[SHIPPING] Error extracting from structured data: {e}")

        if providers:
            logger.info(f"[SHIPPING] Found {len(providers)} from structured data")

        return providers

    async def _extract_from_shipping_sections(self, soup: BeautifulSoup) -> List[ShippingProvider]:
        """Extract from dedicated shipping sections."""
        providers = []

        try:
            # Find sections with shipping-related classes or IDs
            shipping_keywords = [
                "shipping", "delivery", "levering", "forsendelse",
                "fragt", "shipping-option", "delivery-option"
            ]

            for keyword in shipping_keywords:
                sections = soup.find_all(
                    class_=re.compile(keyword, re.I),
                    limit=20  # Limit to prevent processing too many
                )

                for section in sections:
                    # Skip if too large (likely a container)
                    text = section.get_text(strip=True)
                    if len(text) > 1000:
                        continue

                    provider = self._parse_shipping_section(section, text)
                    if provider:
                        providers.append(provider)
        except Exception as e:
            logger.debug(f"[SHIPPING] Error extracting from sections: {e}")

        if providers:
            logger.info(f"[SHIPPING] Found {len(providers)} from shipping sections")

        return providers

    async def _extract_from_radio_buttons(self, soup: BeautifulSoup) -> List[ShippingProvider]:
        """Extract from radio button groups (common in checkouts)."""
        providers = []

        try:
            # Find shipping-related radio buttons
            radios = soup.find_all(
                "input",
                attrs={
                    "type": "radio",
                    "name": re.compile(r"shipping|delivery|levering", re.I)
                }
            )

            for radio in radios:
                # Get label for this radio
                radio_id = radio.get("id")
                label = None

                if radio_id:
                    label = soup.find("label", attrs={"for": radio_id})

                if not label:
                    # Try parent
                    label = radio.find_parent(["label", "div", "li"])

                if label:
                    text = label.get_text(strip=True)
                    provider = self._parse_shipping_text(text)
                    if provider:
                        providers.append(provider)
        except Exception as e:
            logger.debug(f"[SHIPPING] Error extracting from radio buttons: {e}")

        if providers:
            logger.info(f"[SHIPPING] Found {len(providers)} from radio buttons")

        return providers

    async def _extract_from_tables(self, soup: BeautifulSoup) -> List[ShippingProvider]:
        """Extract from table rows (common in checkout pages)."""
        providers = []

        try:
            tables = soup.find_all("table")

            for table in tables:
                rows = table.find_all("tr")

                for row in rows:
                    # Skip header rows
                    if row.find("th"):
                        continue

                    text = row.get_text(strip=True)
                    text_lower = text.lower()

                    # Check if row contains shipping keywords
                    if any(kw in text_lower for kw in ["shipping", "delivery", "levering", "forsendelse"]):
                        provider = self._parse_shipping_text(text)
                        if provider:
                            providers.append(provider)
        except Exception as e:
            logger.debug(f"[SHIPPING] Error extracting from tables: {e}")

        if providers:
            logger.info(f"[SHIPPING] Found {len(providers)} from tables")

        return providers

    async def _extract_from_cards(self, soup: BeautifulSoup, page: Page) -> List[ShippingProvider]:
        """Extract from card/tile layouts (modern UI pattern)."""
        providers = []

        try:
            # Look for card-like structures
            card_selectors = [
                "[class*='card']", "[class*='tile']", "[class*='option']",
                "[class*='method']", "[role='option']", "[role='radio']"
            ]

            for selector in card_selectors:
                cards = soup.select(selector)

                for card in cards[:30]:  # Limit processing
                    text = card.get_text(strip=True)
                    text_lower = text.lower()

                    # Check if card contains shipping info
                    if any(kw in text_lower for kw in ["shipping", "delivery", "levering", "forsendelse"]):
                        # Skip if too large
                        if len(text) > 500:
                            continue

                        provider = self._parse_shipping_section(card, text)
                        if provider:
                            providers.append(provider)
        except Exception as e:
            logger.debug(f"[SHIPPING] Error extracting from cards: {e}")

        if providers:
            logger.info(f"[SHIPPING] Found {len(providers)} from cards")

        return providers

    async def _extract_from_text_blocks(self, soup: BeautifulSoup) -> List[ShippingProvider]:
        """Extract from general text blocks as fallback with stricter filtering."""
        providers = []

        try:
            # Look for containers that likely have shipping options
            shipping_containers = []

            # Find divs/sections with shipping-related classes
            for container in soup.find_all(["div", "section", "ul", "ol"], class_=re.compile(
                r"shipping|delivery|levering|forsendelse|fragt|transport", re.I
            )):
                text = container.get_text(strip=True)
                # Must have reasonable length and contain price OR known provider
                if 30 < len(text) < 800:
                    text_lower = text.lower()
                    has_price = bool(re.search(r"\d+\s*kr", text_lower))
                    has_provider = any(p in text_lower for p in ["postnord", "gls", "dao", "budbee", "burd"])

                    if has_price or has_provider:
                        shipping_containers.append(container)

            # Process each container
            processed_texts = set()

            for container in shipping_containers[:20]:  # Limit processing
                # Look for individual shipping options within container
                options = container.find_all(["div", "li", "label"], recursive=False)

                if options:
                    # Process each option
                    for option in options[:10]:
                        text = option.get_text(strip=True)
                        if text in processed_texts or len(text) < 20 or len(text) > 500:
                            continue
                        processed_texts.add(text)

                        provider = self._parse_shipping_text(text)
                        if provider:
                            providers.append(provider)
                else:
                    # Process container as a whole
                    text = container.get_text(strip=True)
                    if text not in processed_texts:
                        processed_texts.add(text)
                        provider = self._parse_shipping_text(text)
                        if provider:
                            providers.append(provider)

        except Exception as e:
            logger.debug(f"[SHIPPING] Error extracting from text blocks: {e}")

        if providers:
            logger.info(f"[SHIPPING] Found {len(providers)} from text blocks")

        return providers

    def _parse_shipping_detail(self, detail: Dict) -> Optional[ShippingProvider]:
        """Parse structured shipping detail."""
        try:
            name = detail.get("deliveryTime", {}).get("handlingTime", {}).get("value", "Standard Shipping")

            # Extract cost
            cost_data = detail.get("shippingRate", {})
            price = cost_data.get("value")
            currency = cost_data.get("currency", "USD")

            return ShippingProvider(
                name=name,
                price=float(price) if price else None,
                currency=currency if price else None,
                delivery_time="Unknown",
                delivery_type=self._classify_delivery_type(str(detail)),
                description=str(detail)[:200]
            )
        except Exception:
            return None

    def _parse_shipping_section(self, section, text: str) -> Optional[ShippingProvider]:
        """Parse a shipping section element."""
        return self._parse_shipping_text(text)

    def _parse_shipping_text(self, text: str) -> Optional[ShippingProvider]:
        """
        Parse shipping information from text using pattern recognition.

        Args:
            text: Text containing shipping information

        Returns:
            ShippingProvider or None
        """
        if not text or len(text) < 5:
            return None

        text_lower = text.lower()

        # Skip non-shipping content (including cookies, tracking, analytics)
        skip_keywords = [
            "product", "produkt", "quantity", "antal", "add to cart",
            "læg i kurv", "choose", "vælg en", "payment", "betaling",
            "cookie", "tealium", "google analytics", "tracking", "tag manager",
            "acceptér", "godkend", "privacy", "privatliv", "til side",
            "session", "gemmer en", "spar 20%", "binding", "selvbetjening"
        ]

        if any(kw in text_lower for kw in skip_keywords):
            # Unless it also clearly has shipping keywords AND a known provider
            has_shipping = any(kw in text_lower for kw in ["shipping", "delivery", "levering", "forsendelse", "afhent", "hjemlevering"])
            has_provider = any(kw in text_lower for kw in ["postnord", "gls", "dao", "budbee", "burd", "post nord"])
            if not (has_shipping and has_provider):
                return None

        # Extract provider name
        provider_name = self._extract_provider_name(text, text_lower)

        # Extract cost
        cost, currency = self._extract_shipping_cost(text, text_lower)

        # Extract delivery time
        delivery_time = self.data_extractor.extract_delivery_time_with_regex(text)

        # Classify delivery type using standardized types
        delivery_type = self._classify_delivery_type(text_lower)

        # IGNORE ONLY retailer's own store pickups (e.g., "Afhent i Matas butik")
        # BUT allow parcel shop pickups with shippers (e.g., "Afhentning (Postnord)")
        if "afhent" in text_lower and "butik" in text_lower:
            # Only ignore if NO shipper name is present
            temp_provider = self._extract_provider_name(text, text_lower)
            if not temp_provider:
                return None  # No shipper = retailer's own store pickup, ignore it
        if "store pickup" in text_lower or "pick up in store" in text_lower:
            return None

        # Extract provider name
        if not provider_name:
            provider_name = self._extract_provider_name(text, text_lower)

        # Require either a known provider OR cost with shipping context
        has_known_provider = provider_name and any(kw in provider_name.lower() for kw in
            ["postnord", "gls", "dao", "budbee", "burd", "dhl", "ups", "fedex", "dpd"])
        has_shipping_context = any(kw in text_lower for kw in
            ["levering", "delivery", "shipping", "forsendelse", "pakkeshop", "hjemlevering", "ekspres", "express", "håndtering", "palle"])

        # Require at least provider name OR (price + shipping context)
        if not (has_known_provider or (cost is not None and has_shipping_context)):
            return None

        # Determine final name - ONLY shipper name, nothing else
        if provider_name:
            final_name = provider_name  # Just the provider name, no prefixes
        else:
            # No provider name found - skip this option
            return None

        return ShippingProvider(
            name=final_name,
            price=cost,
            currency=currency if cost is not None else None,
            delivery_time=delivery_time or "Unknown",
            delivery_type=delivery_type,
            description=text[:200]
        )

    def _extract_provider_name(self, text: str, text_lower: str) -> Optional[str]:
        """Extract shipping provider name with enhanced Danish support."""
        # Known providers (order matters - check multi-word first)
        known_providers = {
            "burd express": "Burd Express",
            "post nord": "PostNord",
            "postnord": "PostNord",
            "gls": "GLS",
            "dao": "DAO",
            "budbee": "Budbee",
            "bring": "Bring",
            "burd": "Burd",
            "dhl": "DHL",
            "ups": "UPS",
            "fedex": "FedEx",
            "dpd": "DPD",
            "usps": "USPS",
            "royal mail": "Royal Mail",
        }

        providers_found = []

        # First check for parenthesis patterns like "Levering til døren (Postnord)" or "Afhentning (Postnord)"
        parenthesis_matches = re.findall(r"\(([^)]+)\)", text)
        for match in parenthesis_matches:
            match_lower = match.lower()
            for keyword, name in known_providers.items():
                if keyword in match_lower:
                    if name not in providers_found:
                        providers_found.append(name)

        # Check for compound provider patterns like "DAO eller PostNord" or "GLS, DAO eller PostNord"
        compound_patterns = [
            r"\b(dao|gls|postnord|post nord|budbee|burd|dhl|ups)(?:\s+eller\s+|\s*,\s*)(dao|gls|postnord|post nord|budbee|burd|dhl|ups)(?:\s+eller\s+|\s*,\s*)?(dao|gls|postnord|post nord|budbee|burd|dhl|ups)?",
        ]

        for pattern in compound_patterns:
            matches = re.findall(pattern, text_lower, re.I)
            for match_tuple in matches:
                for provider_keyword in match_tuple:
                    if provider_keyword:  # Not None
                        # Normalize
                        provider_keyword = provider_keyword.replace("post nord", "postnord").strip()
                        for keyword, name in known_providers.items():
                            if keyword == provider_keyword.lower():
                                if name not in providers_found:
                                    providers_found.append(name)

        # Then check for standalone provider names
        for keyword, name in known_providers.items():
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, text_lower, re.I):
                if name not in providers_found:
                    providers_found.append(name)

        if len(providers_found) > 1:
            return " / ".join(providers_found)
        elif len(providers_found) == 1:
            return providers_found[0]

        # Try pattern matching
        patterns = [
            r"(?:via|by|with|med)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)",
            r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s+(?:delivery|shipping|levering)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1)
                # Exclude common words
                if name.lower() not in ["delivery", "shipping", "standard", "express", "fast", "normal", "hurtig"]:
                    return name

        return None

    def _extract_shipping_cost(self, text: str, text_lower: str) -> Tuple[Optional[float], Optional[str]]:
        """Extract shipping cost from text."""
        # Check for free shipping
        free_keywords = ["free", "gratis", "fri levering", "fri fragt", "free shipping", "free delivery"]
        if any(kw in text_lower for kw in free_keywords):
            return 0.0, "DKK"  # Assume DKK for Danish sites

        # Check if this is primarily about delivery time (not price)
        time_only_patterns = [
            r"^\s*\d+[-–]\d+\s+(?:arbejdsdage|hverdage|dage|business\s*days?|days?)\s*$",
            r"leveres\s+(?:inden\s+)?(?:for\s+)?\d+[-–]\d+\s+(?:arbejdsdage|hverdage|dage)",
        ]

        for pattern in time_only_patterns:
            if re.search(pattern, text_lower):
                # Unless there's also a price
                if not re.search(r"\d+\s*(?:kr|dkk|€|£|\$)", text_lower):
                    return None, None

        # Handle "Fra X kr" patterns (from X kr)
        fra_match = re.search(r"fra\s+(\d+)\s*(?:kr|dkk)", text_lower)
        if fra_match:
            cost = float(fra_match.group(1))
            if 0 <= cost <= 500:  # Reasonable shipping cost range
                return cost, "DKK"

        # Try to extract price
        price_tuple = self.data_extractor.extract_price_with_regex(text)

        if price_tuple:
            cost, currency = price_tuple

            # Validate: shipping costs typically between 0-500 in local currency
            if 0 <= cost <= 500:
                # Check it's not a product price or other non-shipping cost
                exclude_keywords = [
                    "total", "sum", "subtotal", "minimum", "mindste",
                    "moms", "tax", "vat", "rabat", "discount", "i alt"
                ]

                if not any(kw in text_lower for kw in exclude_keywords):
                    return cost, currency

        return None, None

    def _classify_delivery_type(self, text_lower: str) -> str:
        """Classify delivery type based on text using standardized categories."""
        # 1. Express delivery (check first as it's most specific)
        if any(kw in text_lower for kw in ["ekspres", "express", "hurtig", "same day", "i dag"]):
            return "express-delivery"

        # 2. Business/Company delivery
        elif any(kw in text_lower for kw in ["erhverv", "business", "firma", "company"]):
            return "business"

        # 3. Parcel shop/box/locker
        elif any(kw in text_lower for kw in ["pakkeshop", "pakkeboks", "parcel shop", "parcel box", "parcel locker", "pickup point", "udleveringssted", "afhent"]):
            return "parcel-shop"

        # 4. Home delivery
        elif any(kw in text_lower for kw in ["hjemlevering", "home", "til døren", "door", "address", "levering til"]):
            return "home-delivery"

        # 5. Other (pallet, unknown, etc.)
        else:
            return "Other"

    def _deduplicate_providers(self, providers: List[ShippingProvider]) -> List[ShippingProvider]:
        """Remove duplicate providers."""
        seen = set()
        unique = []

        for provider in providers:
            # Create key from name, price, and delivery type
            key = f"{provider.name}_{provider.price}_{provider.delivery_type}"

            if key not in seen:
                seen.add(key)
                unique.append(provider)

        return unique


class CartManager:
    """Manages add-to-cart and cart navigation."""

    async def add_to_cart(self, page: Page) -> bool:
        """
        Add product to cart with intelligent button detection.

        Args:
            page: Playwright page object

        Returns:
            True if successful, False otherwise
        """
        logger.info("[CART] Attempting to add product to cart...")

        # Step 1: Handle variant selection if needed
        await self._select_variant_if_needed(page)

        # Step 2: Find add-to-cart button
        cart_button = await self._find_add_to_cart_button(page)

        if not cart_button:
            logger.warning("[CART] No add-to-cart button found")
            return False

        # Step 3: Click button
        try:
            await cart_button.click(timeout=5000, no_wait_after=True)
            logger.info("[CART] Clicked add-to-cart button")
            await asyncio.sleep(2.0)  # Wait for cart update/modal

            # Check if a cart modal appeared
            try:
                # Look for checkout button in modal or sidebar
                checkout_btn = await page.query_selector('a[href*="checkout"], a[href*="levering"], button:has-text("checkout"), button:has-text("gå til kassen"), a:has-text("gå til levering")')
                if checkout_btn and await checkout_btn.is_visible():
                    logger.info("[CART] Found checkout button in cart modal, clicking...")
                    await checkout_btn.click(timeout=3000)
                    await asyncio.sleep(1.5)
            except Exception as e:
                logger.debug(f"[CART] No checkout button in modal: {e}")

            return True
        except Exception as e:
            logger.warning(f"[CART] Failed to click add-to-cart: {e}")

            # Try force click
            try:
                await cart_button.click(force=True, no_wait_after=True)
                logger.info("[CART] Force-clicked add-to-cart button")
                await asyncio.sleep(1.0)
                return True
            except Exception as e2:
                logger.error(f"[CART] Force click also failed: {e2}")
                return False

    async def _select_variant_if_needed(self, page: Page) -> bool:
        """Select product variant if required."""
        logger.info("[CART] Checking for variants...")

        variant_selectors = [
            "select.variation_select",
            "select[name*='attribute']",
            "select[name*='variant']",
            ".product-options select",
            ".variants select",
        ]

        for selector in variant_selectors:
            try:
                variant = await page.query_selector(selector)
                if variant and await variant.is_visible():
                    # Select first available option (not "Choose an option")
                    await variant.select_option(index=1)
                    logger.info("[CART] Selected variant")
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue

        return False

    async def _find_add_to_cart_button(self, page: Page) -> Optional[Any]:
        """Find add-to-cart button using multiple strategies."""
        # Strategy 1: Use JavaScript to find button by text content
        logger.info("[CART] Using JavaScript to find add-to-cart button...")

        # Set up console message listener to capture JavaScript console.log
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[JS] {msg.text}"))

        button_info = await page.evaluate("""() => {
            const cartTexts = [
                // English variations
                'add to cart', 'add to basket', 'buy now', 'purchase', 'add', 'buy', 'order now',
                'add to bag', 'shop now', 'get it now', 'checkout', 'proceed to checkout',

                // Danish variations (Denmark/Nordic)
                'læg i kurv', 'læg i indkøbskurven', 'læg i indkøbskurv', 'læg i inkøbskurven',
                'tilføj til kurv', 'tilføj til indkøbskurv', 'køb nu', 'køb', 'bestil nu', 'bestil',
                'til kurven', 'i kurven', 'læg i', 'tilføj', 'put i kurv', 'tilføj i kurv',

                // German variations
                'in den warenkorb', 'zum warenkorb', 'jetzt kaufen', 'kaufen', 'bestellen',

                // French variations
                'ajouter au panier', 'acheter', 'acheter maintenant', 'commander',

                // Swedish variations
                'lägg i varukorg', 'köp nu', 'beställ', 'lägg till',

                // Norwegian variations
                'legg i handlekurv', 'kjøp nå', 'bestill', 'legg til'
            ];

            // Get ALL buttons/inputs in the document
            const allElements = document.querySelectorAll('button, input[type="submit"], [role="button"]');

            let bestMatch = null;
            let bestScore = -1000;  // Start with very negative score

            for (const el of allElements) {
                const text = (el.textContent || el.value || '').toLowerCase().trim();

                // Skip if text is too long (likely not a button)
                if (text.length > 100) continue;

                // Skip if text is too short (likely an icon)
                if (text.length < 3) continue;

                // Check if contains cart text
                const hasCartText = cartTexts.some(ct => text.includes(ct));
                if (!hasCartText) continue;

                // Check if visible
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                // Score this element
                let score = 0;

                // CRITICAL EXCLUSIONS - Heavy penalties
                const inHeader = el.closest('header, [role="banner"]');
                const inNav = el.closest('nav, [role="navigation"], .navigation, .navbar, .header-nav, .menu');
                const inFooter = el.closest('footer, [role="contentinfo"]');
                const inSidebar = el.closest('aside, .sidebar');

                // If in header/nav/footer, give MASSIVE penalty
                if (inHeader) {
                    console.log('REJECTED - in header:', text);
                    continue;  // Skip entirely
                }
                if (inNav) {
                    console.log('REJECTED - in nav:', text);
                    continue;  // Skip entirely
                }
                if (inFooter) {
                    console.log('REJECTED - in footer:', text);
                    continue;  // Skip entirely
                }

                // POSITIVE SCORING for good locations
                const inMain = el.closest('main, [role="main"]');
                const inProduct = el.closest('[class*="product"], [id*="product"], [itemtype*="Product"], article');
                const inContent = el.closest('.content, .main-content, #content, #main');

                // Base score for not being excluded
                score = 50;

                if (inMain) {
                    score += 100;  // Strong preference for main tag
                    console.log('Found in main:', text);
                }
                if (inProduct) {
                    score += 150;  // Even stronger preference for product area
                    console.log('Found in product area:', text);
                }
                if (inContent) {
                    score += 75;
                }
                if (inSidebar) {
                    score -= 200;  // Penalty but not fatal
                }

                // Prefer actual button elements
                if (el.tagName === 'BUTTON') score += 30;
                if (el.tagName === 'INPUT') score += 20;

                // Check if near price element (strong indicator)
                const container = el.closest('form, .product, article, main');
                const nearPrice = container?.querySelector('[class*="price"], .price, [itemprop="price"], .pris');
                if (nearPrice) {
                    score += 50;
                    console.log('Found near price:', text);
                }

                // Prefer exact match
                const exactMatch = cartTexts.some(ct => text === ct || text === ct.trim());
                if (exactMatch) score += 20;

                // Prefer elements with add-to-cart related classes/IDs
                const className = (el.className || '').toLowerCase();
                const idName = (el.id || '').toLowerCase();

                if (className.includes('add') && className.includes('cart')) score += 30;
                if (className.includes('add') && className.includes('basket')) score += 30;
                if (className.includes('buy')) score += 20;
                if (idName.includes('add') && idName.includes('cart')) score += 30;

                // Check data attributes
                const hasCartDataAttr = el.hasAttribute('data-add-to-cart') ||
                                       el.hasAttribute('data-product-id') ||
                                       (el.getAttribute('name') || '').includes('add-to-cart');
                if (hasCartDataAttr) score += 40;

                // Check if button is in a form (good sign for product page)
                const inForm = el.closest('form');
                if (inForm) {
                    const formHasPrice = inForm.querySelector('[class*="price"], [itemprop="price"]');
                    if (formHasPrice) score += 60;
                }

                console.log('Button candidate:', text, 'score:', score, 'tag:', el.tagName);

                if (score > bestScore) {
                    bestScore = score;
                    bestMatch = {
                        tag: el.tagName,
                        text: text,
                        class: el.className,
                        id: el.id,
                        name: el.name,
                        score: score
                    };
                }
            }

            // Only return if score is positive
            if (bestMatch && bestMatch.score > 0) {
                console.log('SELECTED BUTTON:', bestMatch.text, 'with score:', bestMatch.score);
                return bestMatch;
            }

            console.log('NO VALID BUTTON FOUND - best score was:', bestScore);
            return null;
        }""")

        # Log console messages from JavaScript
        for msg in console_messages:
            logger.debug(msg)

        if button_info:
            logger.info(f"[CART] Found button: {button_info['text'][:50]} (score: {button_info.get('score', 0)})")

            # CRITICAL: Use text-based selector that EXCLUDES header/nav
            # This ensures we get the product page button, not the menu button
            text_snippet = button_info["text"][:20]

            selectors_to_try = [
                # Prioritize: button in main with text
                f"main {button_info['tag'].lower()}:has-text('{text_snippet}')",
                # Prioritize: button in product area with text
                f"[class*='product'] {button_info['tag'].lower()}:has-text('{text_snippet}')",
                f"[id*='product'] {button_info['tag'].lower()}:has-text('{text_snippet}')",
                # Try article or form containers
                f"article {button_info['tag'].lower()}:has-text('{text_snippet}')",
                f"form {button_info['tag'].lower()}:has-text('{text_snippet}')",
            ]

            # Try ONLY if it has unique ID or name (safer)
            if button_info.get("id"):
                selectors_to_try.insert(0, f"#{button_info['id']}")

            if button_info.get("name"):
                selectors_to_try.insert(0, f"[name='{button_info['name']}']")

            # Try each selector and VERIFY it's not in header
            for selector in selectors_to_try:
                try:
                    button = await page.query_selector(selector)
                    if button and await button.is_visible():
                        # VERIFY: Check button is NOT in header/nav
                        is_in_header = await button.evaluate("""(el) => {
                            const inHeader = el.closest('header, [role="banner"]');
                            const inNav = el.closest('nav, [role="navigation"], .navigation, .navbar');
                            return !!(inHeader || inNav);
                        }""")

                        if is_in_header:
                            logger.warning(f"[CART] Selector {selector} found button in header/nav, skipping")
                            continue

                        logger.info(f"[CART] [OK] Verified button NOT in header, using selector: {selector}")
                        return button
                except Exception as e:
                    logger.debug(f"[CART] Selector {selector} failed: {e}")
                    continue
        else:
            logger.warning("[CART] JavaScript returned null - no button with positive score found")

        # Strategy 2: Fallback to common selectors
        fallback_selectors = [
            # English
            'button:has-text("Add to Cart")',
            'button:has-text("Add to Basket")',
            'button:has-text("Buy Now")',
            'button:has-text("Add")',

            # Danish - common variations
            'button:has-text("Læg i kurv")',
            'button:has-text("Læg i indkøbskurven")',
            'button:has-text("Læg i inkøbskurven")',
            'button:has-text("Tilføj til kurv")',
            'button:has-text("Køb nu")',
            'button:has-text("Køb")',
            'button:has-text("Bestil")',

            # Generic selectors
            ".add-to-cart-button",
            ".btn-add-to-cart",
            'button[name="add-to-cart"]',
            'input[name="add-to-cart"]',
            'button[class*="add-to-cart"]',
            'button[class*="add-cart"]',
            'button[id*="add-to-cart"]',
        ]

        for selector in fallback_selectors:
            try:
                button = await page.query_selector(selector)
                if button and await button.is_visible():
                    logger.info(f"[CART] Using fallback selector: {selector}")
                    return button
            except Exception as e:
                logger.debug(f"[CART] Fallback selector {selector} failed: {e}")
                continue

        # Strategy 3: Try case-insensitive search for ANY button with "kurv" or "køb" or "add"
        logger.info("[CART] Trying case-insensitive button search...")
        try:
            all_buttons = await page.query_selector_all('button, input[type="submit"], [role="button"], a[class*="button"]')
            for btn in all_buttons:
                try:
                    if not await btn.is_visible():
                        continue

                    text = await btn.text_content()
                    if not text:
                        continue

                    text_lower = text.lower().strip()

                    # Check if contains cart/buy keywords
                    keywords = ['kurv', 'køb', 'add', 'buy', 'bestil', 'tilføj', 'cart', 'basket', 'purchase']
                    if any(keyword in text_lower for keyword in keywords):
                        # Verify NOT in header/nav
                        is_in_header = await btn.evaluate("""(el) => {
                            const inHeader = el.closest('header, nav, [role="banner"], [role="navigation"]');
                            return !!inHeader;
                        }""")

                        if not is_in_header:
                            logger.info(f"[CART] Found button via keyword search: '{text[:50]}'")
                            return btn
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[CART] Keyword search failed: {e}")

        return None

    async def navigate_to_checkout(self, page: Page, base_url: str) -> bool:
        """
        Navigate to checkout page using discovered paths.

        Args:
            page: Playwright page object
            base_url: Base URL of the website

        Returns:
            True if successful, False otherwise
        """
        logger.info("[CART] Navigating to checkout...")

        # Strategy 1: Try clicking checkout/cart button first (most reliable)
        try:
            checkout_button_selectors = [
                'a:has-text("Gå til kassen")',
                'a:has-text("Til kassen")',
                'button:has-text("Gå til kassen")',
                'button:has-text("Til kassen")',
                'a:has-text("Checkout")',
                'a:has-text("Go to checkout")',
                'button:has-text("Checkout")',
                'a:has-text("Proceed to checkout")',
                'a[href*="checkout"]',
                'a[href*="kassen"]',
                'a[href*="levering"]',
                '.checkout-button',
                '.proceed-to-checkout',
                '[data-testid*="checkout"]',
            ]

            for selector in checkout_button_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button and await button.is_visible():
                        logger.info(f"[CART] Found checkout button: {selector}")
                        await button.click()
                        await asyncio.sleep(2.0)

                        # Check if navigation was successful
                        current_url = page.url.lower()
                        if any(kw in current_url for kw in ["checkout", "kassen", "levering", "shipping", "delivery", "cart"]):
                            logger.info(f"[CART] Successfully navigated via button to: {page.url}")
                            return True
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[CART] Checkout button strategy failed: {e}")

        # Strategy 2: Use discovered URLs
        discovery = CheckoutPathDiscovery()
        checkout_urls = await discovery.discover_checkout_urls(page, base_url)

        # Try each URL
        for url in checkout_urls:
            try:
                logger.info(f"[CART] Trying checkout URL: {url}")

                # Add a longer wait to ensure cart is ready
                await asyncio.sleep(1.5)

                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2.0)

                # Check if we're on a checkout page - be more lenient
                current_url = page.url.lower()
                page_content = await page.content()

                # Check URL or page content for checkout indicators
                url_check = any(kw in current_url for kw in ["checkout", "kassen", "levering", "shipping", "delivery", "cart"])
                content_check = any(kw in page_content.lower() for kw in ["leveringsadresse", "shipping address", "delivery address", "leveringsmåde"])

                if url_check or content_check:
                    logger.info(f"[CART] Successfully navigated to checkout: {page.url}")
                    return True
            except Exception as e:
                logger.debug(f"[CART] Failed to navigate to {url}: {e}")
                continue

        logger.warning("[CART] Could not navigate to checkout")
        return False


class FormFiller:
    """Fills checkout forms with test data."""

    def __init__(self, shipping_extractor):
        """Initialize with reference to shipping extractor."""
        self.shipping_extractor = shipping_extractor

    async def fill_checkout_form(self, page: Page, max_steps: int = 5) -> List[ShippingProvider]:
        """
        Fill checkout form and progress through steps, checking for shipping options at each step.

        Args:
            page: Playwright page object
            max_steps: Maximum number of checkout steps to process

        Returns:
            List of shipping providers found during checkout steps
        """
        logger.info("[FORM] Filling checkout form...")

        all_shipping_providers = []

        test_data = {
            "email": settings.test_email,
            "first_name": settings.test_first_name,
            "last_name": settings.test_last_name,
            "phone": settings.test_phone,
            "address": settings.test_address,
            "postal_code": settings.test_postal_code,
            "city": settings.test_city,
            "combined_name": f"{settings.test_first_name} {settings.test_last_name}",
        }

        for step in range(max_steps):
            logger.info(f"[FORM] Processing step {step + 1}/{max_steps}...")

            fields_filled = 0

            # Fill email
            fields_filled += await self._fill_field(
                page,
                ['input[type="email"]', 'input[name*="email"]', '#email'],
                test_data["email"]
            )

            # Fill name (try combined first, then separate)
            combined_filled = await self._fill_field(
                page,
                ['input[name*="name"]:not([name*="first"]):not([name*="last"])', '#name'],
                test_data["combined_name"]
            )

            if combined_filled:
                fields_filled += combined_filled
            else:
                # Fill first and last separately
                fields_filled += await self._fill_field(
                    page,
                    ['input[name*="first"]', '#firstName', '#first-name'],
                    test_data["first_name"]
                )

                fields_filled += await self._fill_field(
                    page,
                    ['input[name*="last"]', '#lastName', '#last-name'],
                    test_data["last_name"]
                )

            # Fill phone
            fields_filled += await self._fill_field(
                page,
                ['input[type="tel"]', 'input[name*="phone"]', '#phone'],
                test_data["phone"]
            )

            # Fill address
            fields_filled += await self._fill_field(
                page,
                ['input[name*="address"]', '#address', '#street'],
                test_data["address"]
            )

            # Fill postal code
            fields_filled += await self._fill_field(
                page,
                ['input[name*="postal"]', 'input[name*="zip"]', '#postalCode', '#zip'],
                test_data["postal_code"]
            )

            # Fill city
            fields_filled += await self._fill_field(
                page,
                ['input[name*="city"]', '#city'],
                test_data["city"]
            )

            logger.info(f"[FORM] Filled {fields_filled} fields at step {step + 1}")

            # Look for "Next" or "Continue" button
            next_clicked = await self._click_next_button(page)

            if next_clicked:
                logger.info("[FORM] Clicked next button, waiting for page update...")
                await asyncio.sleep(2.0)  # Wait for new content to load

                # CHECK FOR SHIPPING OPTIONS AFTER EACH NEXT CLICK
                logger.info(f"[FORM] Checking for shipping options after step {step + 1}...")
                try:
                    # Get current page HTML
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")

                    # Try to extract shipping options
                    shipping_providers = await self.shipping_extractor.extract_shipping_info(
                        page, soup, context=f"checkout_step_{step + 1}"
                    )

                    if shipping_providers:
                        logger.info(f"[FORM] Found {len(shipping_providers)} shipping options at step {step + 1}!")
                        all_shipping_providers.extend(shipping_providers)
                        # If we found shipping options, we can stop progressing through more steps
                        break
                except Exception as e:
                    logger.debug(f"[FORM] Error checking shipping at step {step + 1}: {e}")
            else:
                # No next button, we're done
                if fields_filled == 0:
                    logger.info("[FORM] No more fields to fill")
                    break
                else:
                    # Filled some fields but no next button - might be single-page checkout
                    logger.info("[FORM] No next button found, might be single-page checkout")
                    break

        logger.info("[FORM] Checkout form processing complete")
        logger.info(f"[FORM] Collected {len(all_shipping_providers)} shipping providers during form steps")
        return all_shipping_providers

    async def _fill_field(self, page: Page, selectors: List[str], value: str) -> int:
        """Fill a form field if found."""
        for selector in selectors:
            try:
                field = await page.query_selector(selector)
                if field and await field.is_visible():
                    current_value = await field.input_value()
                    if not current_value:
                        await field.fill(value)
                        logger.debug(f"[FORM] Filled field: {selector}")
                        return 1
            except Exception:
                continue

        return 0

    async def _click_next_button(self, page: Page) -> bool:
        """Click next/continue button if found."""
        next_texts = [
            "next", "continue", "næste", "fortsæt", "videre",
            "proceed", "weiter", "suivant", "continuar"
        ]

        for text in next_texts:
            try:
                button = await page.query_selector(f'button:has-text("{text}")')
                if not button:
                    button = await page.query_selector(f'a:has-text("{text}")')

                if button and await button.is_visible() and await button.is_enabled():
                    await button.click()
                    logger.info(f"[FORM] Clicked '{text}' button")
                    return True
            except Exception:
                continue

        return False


class ScraperService:
    """
    Universal intelligent scraper that adapts to different websites.

    This service uses adaptive strategies to work across all e-commerce sites,
    intelligently discovering checkout paths and extracting shipping information
    from various UI patterns.
    """

    def __init__(self, headless: bool = True, screenshot: bool = False):
        self.headless = headless
        self.screenshot = screenshot
        self.playwright = None
        self.browser = None

        # Initialize components
        self.product_extractor = ProductExtractor()
        self.shipping_extractor = ShippingExtractor()
        self.cart_manager = CartManager()
        self.form_filler = FormFiller(self.shipping_extractor)  # Pass shipping extractor

        if self.screenshot:
            Path("screenshots").mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Start Playwright and browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)

        logger.info("[OK] Browser started")

    async def close(self):
        """Close browser and Playwright."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

        logger.info("[OK] Browser closed")

    async def scrape(self, analysis: AnalysisResult) -> Optional[ScrapedProduct]:
        """
        Scrape a product using intelligent adaptive methods.

        Args:
            analysis: AnalysisResult from analyzer service

        Returns:
            ScrapedProduct or None
        """
        product_url = analysis.product_url
        source_website = analysis.source_website

        logger.info(f"=== Starting intelligent scrape for {source_website} ===")
        logger.info(f"URL: {product_url}")

        try:
            # Ensure browser is started
            if not self.browser:
                await self.start()

            # Create new page
            page = await self.browser.new_page()
            page.set_default_timeout(30000)

            # Navigate to product page
            logger.info("[PAGE] Loading product page...")
            await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(1.0)  # Wait for dynamic content

            # Dismiss cookie banner
            await self._dismiss_cookies(page)

            # Get page content
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Extract product information
            product_info = await self.product_extractor.extract_product_info(page, soup, product_url)

            if not product_info.get("title") or not product_info.get("price"):
                logger.warning("[PRODUCT] Could not extract basic product info")
                await page.close()
                return None

            # SKIP product page shipping - go straight to checkout for accurate shipping options
            logger.info("[SHIPPING] Skipping product page - will extract from checkout...")
            shipping_providers = []

            # Go to cart/checkout flow to get shipping options
            logger.info("[CART] Starting cart flow to reach checkout...")

            # Add to cart
            cart_success = await self.cart_manager.add_to_cart(page)

            if cart_success:
                # Navigate to checkout
                base_url = f"{urlparse(product_url).scheme}://{urlparse(product_url).netloc}"
                checkout_success = await self.cart_manager.navigate_to_checkout(page, base_url)

                if checkout_success:
                    # Dismiss cookies again (might appear on checkout)
                    await self._dismiss_cookies(page)

                    # Expand any collapsed sections
                    await self._expand_shipping_sections(page)

                    # Fill checkout form AND extract shipping during form steps
                    shipping_providers_from_form = await self.form_filler.fill_checkout_form(page)

                    # Use shipping providers found during form filling
                    if shipping_providers_from_form:
                        logger.info(f"[SHIPPING] Using {len(shipping_providers_from_form)} providers found during form steps")
                        shipping_providers = shipping_providers_from_form
                    else:
                        # Fallback: try extracting from final checkout page
                        logger.info("[SHIPPING] No providers found during form, trying final checkout page...")

                        # Wait a bit more for any late-loading content
                        await asyncio.sleep(2.0)

                        # Extract shipping from final checkout page
                        checkout_html = await page.content()
                        checkout_soup = BeautifulSoup(checkout_html, "html.parser")

                        # DEBUG: Save checkout HTML to inspect
                        debug_html_path = f"screenshots/checkout_debug_{source_website}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                        with open(debug_html_path, "w", encoding="utf-8") as f:
                            f.write(checkout_html)
                        logger.info(f"[DEBUG] Saved checkout HTML to {debug_html_path}")

                        shipping_providers = await self.shipping_extractor.extract_shipping_info(
                            page, checkout_soup, context="checkout_final"
                        )

            # Take screenshot if enabled
            screenshot_path = None
            if self.screenshot:
                screenshot_path = f"screenshots/{source_website}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot_path)
                logger.info(f"[SCREENSHOT] Saved to {screenshot_path}")

            # Close page
            await page.close()

            # Build result
            scraped_product = ScrapedProduct(
                title=product_info["title"],
                price=product_info["price"],
                currency=product_info["currency"],
                url=product_url,
                source_website=source_website,
                description=product_info.get("description"),
                image_url=product_info.get("image"),
                shipping_providers=shipping_providers,
                scraped_at=datetime.now(),
                screenshot_path=screenshot_path,
            )

            logger.info(f"[OK] Successfully scraped: {product_info['title']}")
            logger.info(f"[OK] Found {len(shipping_providers)} shipping options")

            return scraped_product

        except Exception as e:
            logger.error(f"[ERROR] Error scraping {product_url}: {e}")
            logger.debug(traceback.format_exc())
            return None

    async def _dismiss_cookies(self, page: Page) -> bool:
        """Dismiss cookie consent banner if present."""
        logger.debug("[COOKIES] Checking for cookie banner...")

        # Wait longer for banner to appear (especially for slow-loading sites)
        await asyncio.sleep(1.0)

        cookie_selectors = settings.cookie_selectors

        # Try to dismiss in main page first
        for selector in cookie_selectors:
            try:
                button = await page.query_selector(selector)
                if button and await button.is_visible():
                    await button.click(timeout=2000)
                    logger.info(f"[COOKIES] Dismissed: {selector}")
                    await asyncio.sleep(0.5)  # Wait for banner to disappear
                    return True
            except Exception as e:
                logger.debug(f"[COOKIES] Failed to click {selector}: {e}")
                continue

        # Try in iframes if not found in main page (some sites use iframe for cookie consent)
        try:
            frames = page.frames
            for frame in frames:
                for selector in cookie_selectors:
                    try:
                        button = await frame.query_selector(selector)
                        if button and await button.is_visible():
                            await button.click(timeout=2000)
                            logger.info(f"[COOKIES] Dismissed in iframe: {selector}")
                            await asyncio.sleep(0.5)
                            return True
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"[COOKIES] Error checking iframes: {e}")

        logger.debug("[COOKIES] No cookie banner found")
        return False

    async def _expand_shipping_sections(self, page: Page) -> None:
        """Expand collapsed shipping sections on checkout pages."""
        logger.info("[EXPAND] Expanding shipping sections...")

        try:
            # Find and click expandable elements
            expandable_selectors = [
                "details:not([open])",
                "[aria-expanded='false']",
                ".collapsed",
                "button:has-text('shipping')",
                "button:has-text('delivery')",
                "button:has-text('levering')",
            ]

            expanded_count = 0

            for selector in expandable_selectors:
                try:
                    elements = await page.query_selector_all(selector)

                    for element in elements[:10]:  # Limit to prevent too many clicks
                        try:
                            if await element.is_visible():
                                await element.click()
                                expanded_count += 1
                                await asyncio.sleep(0.3)
                        except Exception:
                            continue
                except Exception:
                    continue

            if expanded_count > 0:
                logger.info(f"[EXPAND] Expanded {expanded_count} sections")
        except Exception as e:
            logger.debug(f"[EXPAND] Error: {e}")

    async def scrape_multiple(self, analyses: List[AnalysisResult]) -> List[ScrapedProduct]:
        """Scrape multiple products concurrently."""
        logger.info(f"=== Scraping {len(analyses)} products ===")

        tasks = [self.scrape(analysis) for analysis in analyses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        products = []
        for i, result in enumerate(results):
            if isinstance(result, ScrapedProduct):
                products.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Product {i+1} failed: {result}")
            else:
                logger.warning(f"Product {i+1} returned None")

        logger.info(f"[OK] Successfully scraped {len(products)}/{len(analyses)} products")

        return products

