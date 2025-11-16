"""
Product Scraper Service
Scrapes products using Playwright async API
Accepts AnalysisResult, returns ScrapedProduct (both Kafka-ready)
"""
import logging
import asyncio
import traceback
from typing import List, Optional
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup

from src.schemas.messages import AnalysisResult, ScrapedProduct, ShippingProvider
from src.utils.extractors import DataExtractor
from src.config import settings

logger = logging.getLogger(__name__)


class ScraperService:
    """Service for product scraping using Playwright with retry and fallback mechanisms"""

    def __init__(self, headless: bool = True, screenshot: bool = False, max_retries: int = None, timeout: int = None):
        self.headless = headless
        self.screenshot = screenshot
        self.max_retries = max_retries or settings.max_retries
        self.timeout = timeout or settings.page_timeout
        self.playwright = None
        self.browser = None
        self.data_extractor = DataExtractor()

        # Create screenshots directory if needed
        if self.screenshot:
            screenshots_dir = Path("screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Start Playwright and browser."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        logger.info(" Browser started")

    async def close(self):
        """Close browser and Playwright."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info(" Browser closed")

    async def scrape(self, analysis: AnalysisResult) -> Optional[ScrapedProduct]:
        """
        Scrape a single product based on AnalysisResult with retry logic.

        Args:
            analysis: AnalysisResult Pydantic schema from analyzer

        Returns:
            ScrapedProduct Pydantic schema (or None on failure)
        """
        product_url = analysis.product_url
        source_website = analysis.source_website
        selectors = analysis.selectors
        delay = analysis.scrape_delay

        logger.info(f" Starting scrape for {source_website}")
        logger.info(f"[URL] {product_url}")

        # Retry loop with exponential backoff
        for attempt in range(self.max_retries):
            try:
                # Ensure browser is started
                if not self.browser:
                    await self.start()

                # Create new page with timeout
                page = await self.browser.new_page()
                page.set_default_timeout(self.timeout)

                # Navigate to product page with retry
                logger.info(f"Loading page... (Attempt {attempt + 1}/{self.max_retries})")
                try:
                    await page.goto(product_url, wait_until="domcontentloaded", timeout=self.timeout)
                except PlaywrightTimeoutError:
                    logger.warning(f"Page load timeout on attempt {attempt + 1}")
                    await page.close()
                    if attempt < self.max_retries - 1:
                        wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.info(f"Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error("Max retries reached for page load")
                        return None

                # Wait for dynamic content
                logger.info(f"Waiting {settings.dynamic_content_wait}s for dynamic content...")
                await asyncio.sleep(settings.dynamic_content_wait)

                # Handle cookie consent banners that might hide add-to-cart buttons
                logger.info("[COOKIE] Checking for and dismissing cookie consent banners...")
                await self._dismiss_cookie_banner_if_needed(page, context="INITIAL_PAGE")

                # Extract product information
                logger.info("Extracting product data...")

                # Get page content
                html_content = await page.content()
                soup = BeautifulSoup(html_content, "html.parser")

                # Extract with fallback mechanisms
                title = await self._extract_title(soup, page)
                price, currency = await self._extract_price(soup, page)
                description = await self._extract_description(soup)
                image_url = await self._extract_image(soup)

                # Try to extract shipping from cart/checkout (more accurate)
                shipping_providers = await self._extract_shipping_from_cart(page, soup)

                # If cart extraction fails/not supported, fall back to page extraction
                if not shipping_providers:
                    shipping_providers = await self._extract_shipping_providers(soup)

                if not title:
                    logger.error("Failed to extract product title - critical field missing")
                    await page.close()
                    if attempt < self.max_retries - 1:
                        logger.info("Retrying extraction...")
                        continue
                    return None

                # Take screenshot if enabled
                screenshot_path = None
                if self.screenshot:
                    try:
                        screenshot_path = f"screenshots/{source_website}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        await page.screenshot(path=screenshot_path)
                        logger.info(f"Screenshot saved: {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"Failed to save screenshot: {e}")
                        # Continue even if screenshot fails

                await page.close()

                # Create ScrapedProduct schema
                scraped_product = ScrapedProduct(
                    title=title,
                    price=price or 0.0,  # Pydantic requires float, default to 0
                    currency=currency or "USD",
                    url=product_url,
                    source_website=source_website,
                    scraped_at=datetime.now(),
                    screenshot_path=screenshot_path,
                    shipping_providers=shipping_providers,
                    scraper_metadata={
                        "selectors_used": selectors,
                        "scrape_delay": delay,
                        "image_url": image_url,
                        "description": description,
                        "availability": "in stock",
                        "extraction_attempt": attempt + 1,
                    },
                )

                logger.info(f" Successfully scraped: {scraped_product.title}")

                # Future: Publish to Kafka topic 'scraped-products'
                # await kafka_producer.send('scraped-products', scraped_product.model_dump_json())

                return scraped_product

            except Exception as e:
                logger.error(f"Error during scraping (attempt {attempt + 1}/{self.max_retries}): {e}")
                logger.debug(f"Stack trace: {traceback.format_exc()}")

                if attempt < self.max_retries - 1:
                    wait_time = 2**attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("Max retries reached, scraping failed")
                    return None

        return None

    async def _extract_title(self, soup: BeautifulSoup, page) -> Optional[str]:
        """
        Extract product title using multiple fallback strategies.

        Tries in order:
        1. h1 tag (most common for product pages)
        2. Elements with 'product' and 'title' in class name
        3. Open Graph meta title (og:title)
        4. h2 tag as last resort

        Args:
            soup: BeautifulSoup parsed HTML of product page
            page: Playwright page object for dynamic content

        Returns:
            Product title string or None if extraction fails
        """
        try:
            # Strategy 1: h1 tag
            title_elem = soup.find("h1")
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    return title

            # Strategy 2: Product title class
            title_elem = soup.find(
                class_=lambda x: x and "product" in x.lower() and "title" in x.lower() if x else False
            )
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    logger.info("Used fallback: product title class")
                    return title

            # Strategy 3: Page title meta tag
            meta_title = soup.find("meta", property="og:title")
            if meta_title and meta_title.get("content"):
                logger.info("Used fallback: meta og:title")
                return meta_title.get("content")

            # Strategy 4: h2 as last resort
            title_elem = soup.find("h2")
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    logger.warning("Used fallback: h2 tag (low confidence)")
                    return title

            return None
        except Exception as e:
            logger.error(f"Error extracting title: {e}")
            return None

    async def _extract_price(self, soup: BeautifulSoup, page) -> tuple[Optional[float], Optional[str]]:
        """
        Extract product price and currency using multiple fallback strategies.
        Prioritizes main product price and filters out related products, membership prices, etc.

        Tries in order:
        1. Schema.org structured data (JSON-LD) - most reliable
        2. Open Graph meta tags
        3. WooCommerce-specific price elements (with filtering)
        4. itemprop price attribute
        5. Elements with 'price' in class name (with strict filtering)

        Args:
            soup: BeautifulSoup parsed HTML of product page
            page: Playwright page object

        Returns:
            Tuple of (price_float, currency_code) or (None, None) if not found
        """
        try:
            # Strategy 1: Schema.org JSON-LD structured data (most reliable)
            json_ld_price = self._extract_price_from_json_ld(soup)
            if json_ld_price:
                logger.info("Used Schema.org JSON-LD for price")
                return json_ld_price

            # Strategy 2: meta og:price (second most reliable)
            meta_price = soup.find("meta", property="og:price:amount")
            if meta_price and meta_price.get("content"):
                try:
                    price = float(meta_price.get("content"))
                    currency_meta = soup.find("meta", property="og:price:currency")
                    currency = currency_meta.get("content") if currency_meta else "USD"
                    logger.info("Used meta og:price")
                    return price, currency
                except ValueError:
                    pass

            # Strategy 3: itemprop price (structured data)
            price_elem = soup.find(attrs={"itemprop": "price"})
            if price_elem:
                price_text = price_elem.get_text(strip=True) or price_elem.get("content", "")
                if self._is_valid_price_context(price_elem):
                    price_tuple = self.data_extractor.extract_price_with_regex(price_text)
                    if price_tuple:
                        logger.info("Used itemprop price")
                        return price_tuple

            # Strategy 4: WooCommerce specific price elements (prioritize current price)
            # First, try to find the current/active price (not old/strikethrough)
            price_elem = soup.select_one(
                ".woocommerce-Price-amount.amount:not(del .amount):not(.was .amount), "
                ".price ins .amount, "
                ".price .amount:not(del .amount)"
            )
            if price_elem and self._is_main_product_price(price_elem):
                price_text = price_elem.get_text(strip=True)
                price_tuple = self.data_extractor.extract_price_with_regex(price_text)
                if price_tuple:
                    logger.info("Used WooCommerce price selector")
                    return price_tuple

            # Strategy 5: WooCommerce variation price (often in select options or table)
            variation_prices = soup.select(".variations select option, .variations td")
            for elem in variation_prices:
                text = elem.get_text(strip=True)
                # Look for price in format "23kr V/144 stk." or similar
                if "kr" in text.lower() and "v/" in text.lower():
                    # Extract the first price (which is usually the unit price)
                    price_tuple = self.data_extractor.extract_price_with_regex(text.split("V/")[0])
                    if price_tuple:
                        logger.info(f"Used WooCommerce variation price from: {text[:50]}")
                        return price_tuple

            # Strategy 6: Price class (general) with strict filtering
            price_elems = soup.find_all(class_=lambda x: x and "price" in x.lower() if x else False)
            for price_elem in price_elems:
                # Skip if this looks like it's from a related/recommended product section
                if not self._is_main_product_price(price_elem):
                    continue
                
                # Skip if it's an old/comparison price
                if not self._is_valid_price_context(price_elem):
                    continue
                
                price_text = price_elem.get_text(strip=True)
                price_tuple = self.data_extractor.extract_price_with_regex(price_text)
                if price_tuple:
                    logger.info("Used price class selector")
                    return price_tuple

            logger.warning("Could not extract price with any strategy")
            return None, None
        except Exception as e:
            logger.error(f"Error extracting price: {e}")
            return None, None

    def _extract_price_from_json_ld(self, soup: BeautifulSoup) -> Optional[tuple[float, str]]:
        """
        Extract price from Schema.org JSON-LD structured data.
        This is the most reliable source as it's intended for search engines.

        Args:
            soup: BeautifulSoup parsed HTML

        Returns:
            Tuple of (price, currency) or None
        """
        try:
            import json
            
            # Find all JSON-LD script tags
            json_ld_scripts = soup.find_all("script", type="application/ld+json")
            
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    
                    # Handle both single objects and arrays
                    items = data if isinstance(data, list) else [data]
                    
                    for item in items:
                        # Look for Product type
                        if item.get("@type") in ["Product", "ProductModel"]:
                            offers = item.get("offers")
                            
                            if offers:
                                # Handle both single offer and array of offers
                                offer_list = offers if isinstance(offers, list) else [offers]
                                
                                for offer in offer_list:
                                    # Get price and currency
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
        except Exception as e:
            logger.debug(f"Error extracting JSON-LD price: {e}")
            return None

    def _is_main_product_price(self, element) -> bool:
        """
        Check if a price element belongs to the main product, not a related/recommended product.
        
        Args:
            element: BeautifulSoup element containing price
            
        Returns:
            True if this is likely the main product price, False otherwise
        """
        # Check parent containers for indicators of related/recommended products
        parent_text = ""
        parent = element.parent
        
        # Walk up the DOM tree checking for related product indicators
        for _ in range(5):  # Check up to 5 levels up
            if not parent:
                break
                
            parent_class = " ".join(parent.get("class", [])).lower()
            parent_id = parent.get("id", "").lower()
            parent_text = (parent_class + " " + parent_id).lower()
            
            # Exclude if in related/recommended products section
            excluded_keywords = [
                "related", "recommend", "similar", "also-bought", "you-may",
                "cross-sell", "upsell", "bundle", "accessories",
                "recently-viewed", "popular", "trending", "bestseller",
                "widget", "sidebar", "aside"
            ]
            
            if any(keyword in parent_text for keyword in excluded_keywords):
                logger.debug(f"Skipping price from related products section: {parent_text[:50]}")
                return False
            
            parent = parent.parent
        
        return True

    def _is_valid_price_context(self, element) -> bool:
        """
        Check if a price element represents the actual current price,
        not a membership price, old price, or comparison price.
        
        Args:
            element: BeautifulSoup element containing price
            
        Returns:
            True if this is a valid current price, False otherwise
        """
        # Check the element and its immediate parents for indicators
        check_elements = [element]
        parent = element.parent
        for _ in range(3):  # Check element + 3 parent levels
            if parent:
                check_elements.append(parent)
                parent = parent.parent
        
        for elem in check_elements:
            elem_class = " ".join(elem.get("class", [])).lower()
            elem_text = elem.get_text(strip=True).lower()
            
            # Exclude old/strikethrough prices
            if elem.name in ["del", "s", "strike"]:
                logger.debug("Skipping strikethrough/deleted price")
                return False
            
            # Exclude based on class names
            excluded_class_keywords = [
                "old", "was", "before", "original", "regular", "compare",
                "msrp", "rrp", "list-price", "crossed", "strike",
                "member", "membership", "subscription", "subscribe",
                "discount", "save", "you-save"
            ]
            
            if any(keyword in elem_class for keyword in excluded_class_keywords):
                logger.debug(f"Skipping price with excluded class: {elem_class[:50]}")
                return False
            
            # Exclude based on surrounding text context (check only immediate element text)
            if elem == element:
                excluded_text_keywords = [
                    "was", "before", "originally", "regular",
                    "member", "membership", "subscribe", "subscription",
                    "msrp", "rrp", "list price", "compare at"
                ]
                
                if any(keyword in elem_text for keyword in excluded_text_keywords):
                    logger.debug(f"Skipping price with excluded context: {elem_text[:50]}")
                    return False
        
        return True

    async def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract product description using fallback strategies.

        Tries in order:
        1. Elements with 'product_description' class
        2. Meta description tag
        3. First paragraph element as fallback

        Args:
            soup: BeautifulSoup parsed HTML of product page

        Returns:
            Product description text or None
        """
        try:
            # Strategy 1: product_description class
            desc_elem = soup.find(class_="product_description")
            if desc_elem:
                return desc_elem.get_text(strip=True)

            # Strategy 2: meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                return meta_desc.get("content")

            # Strategy 3: first paragraph
            p_elem = soup.find("p")
            if p_elem:
                logger.info("Used fallback: first paragraph for description")
                return p_elem.get_text(strip=True)

            return None
        except Exception as e:
            logger.warning(f"Error extracting description: {e}")
            return None

    async def _extract_image(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract image URL with fallback"""
        try:
            # Strategy 1: img tag
            img_elem = soup.find("img")
            if img_elem:
                return img_elem.get("src")

            # Strategy 2: meta og:image
            meta_img = soup.find("meta", property="og:image")
            if meta_img and meta_img.get("content"):
                logger.info("Used fallback: meta og:image")
                return meta_img.get("content")

            return None
        except Exception as e:
            logger.warning(f"Error extracting image: {e}")
            return None

    def _classify_delivery_type(self, text: str) -> str:
        """
        Classify the delivery type based on text content.

        Args:
            text: Shipping option text (already lowercased)

        Returns:
            Delivery type: "home_delivery", "store_pickup", "parcel_shop", or "parcel_locker"
        """
        # Check in order of specificity
        if any(keyword in text for keyword in settings.parcel_locker_keywords):
            return "parcel_locker"
        elif any(keyword in text for keyword in settings.store_pickup_keywords):
            return "store_pickup"
        elif any(keyword in text for keyword in settings.parcel_shop_keywords):
            return "parcel_shop"
        elif any(keyword in text for keyword in settings.home_delivery_keywords):
            return "home_delivery"
        else:
            # Default to home delivery if unclear
            return "home_delivery"

    async def _expand_shipping_sections(self, page) -> None:
        """
        Try to expand any collapsed shipping sections or cards that might hide shipping details.
        Looks for expand buttons, accordions, or collapsible cards.
        Only expands if it's a simple "show more" action, not navigation buttons.
        """
        try:
            logger.info("[CHECKOUT] Checking for expandable shipping sections...")

            # Common selectors for expand/show buttons in shipping sections
            # Exclude navigation buttons like "Next", "Continue", "Proceed to payment"
            expanded_count = 0
            for selector in settings.expand_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements[:10]:  # Limit to first 10 expandable sections
                        try:
                            is_visible = await element.is_visible()
                            if is_visible:
                                text = await element.text_content() or ""
                                text_lower = text.lower()

                                # Skip if this looks like a navigation button
                                navigation_keywords = [
                                    "næste",
                                    "next",
                                    "fortsæt",
                                    "continue",
                                    "proceed",
                                    "betaling",
                                    "payment",
                                    "checkout",
                                    "til betaling",
                                    "gå til",
                                    "go to",
                                    "submit",
                                    "send",
                                ]
                                if any(keyword in text_lower for keyword in navigation_keywords):
                                    logger.debug(f"[CHECKOUT] Skipping navigation button: {text[:50]}")
                                    continue

                                # Only click if it's related to shipping/delivery or is a details/summary
                                if any(
                                    keyword in text_lower
                                    for keyword in [
                                        "levering",
                                        "shipping",
                                        "delivery",
                                        "forsendelse",
                                        "vis",
                                        "show",
                                        "se",
                                    ]
                                ):
                                    await element.click()
                                    expanded_count += 1
                                    logger.info(f"[CHECKOUT] Expanded section: {text[:50]}")
                        except Exception as e:
                            logger.debug(f"[CHECKOUT] Failed to click expand element: {e}")
                except Exception:
                    continue

            if expanded_count > 0:
                logger.info(f"[CHECKOUT] Expanded {expanded_count} shipping sections")
                # Check for cookie popups after expanding sections
                await asyncio.sleep(0.3)
                await self._dismiss_cookie_banner_if_needed(page, context="EXPAND_SHIPPING")
            else:
                logger.info("[CHECKOUT] No expandable sections found or all already expanded")

        except Exception as e:
            logger.debug(f"[CHECKOUT] Error expanding shipping sections: {e}")

    async def _fill_checkout_details_if_needed(self, page) -> None:
        """
        Fill in required checkout details (email, name, address) and progress through checkout steps.
        This handles multi-step checkouts that require customer information before showing shipping options with prices.
        Will click "Next" or "Continue" buttons to progress through all checkout steps until shipping prices are visible.
        """
        try:
            logger.info("[CHECKOUT] Starting multi-step checkout process...")

            # Test data for checkout forms (from config)
            test_data = {
                "email": settings.test_email,
                "first_name": settings.test_first_name,
                "last_name": settings.test_last_name,
                "phone": settings.test_phone,
                "address": settings.test_address,
                "postal_code": settings.test_postal_code,
                "city": settings.test_city,
                "country": settings.test_country,
                "first_and_last_name": f"{settings.test_first_name} {settings.test_last_name}",
            }

            # Try up to max checkout steps (most checkouts have 2-3 steps)
            max_steps = settings.max_checkout_steps
            for step in range(max_steps):
                logger.info(f"[CHECKOUT] Processing step {step + 1}/{max_steps}...")

                # Debug: Log all visible input fields on the page
                try:
                    all_inputs = await page.query_selector_all(
                        'input[type="text"], input[type="email"], input[type="tel"]'
                    )
                    logger.info(f"[CHECKOUT] Found {len(all_inputs)} text/email/tel input fields on page")
                    for idx, inp in enumerate(all_inputs[:10]):  # Log first 10 only
                        is_vis = await inp.is_visible()
                        if is_vis:
                            name = await inp.get_attribute("name")
                            placeholder = await inp.get_attribute("placeholder")
                            input_id = await inp.get_attribute("id")
                            logger.info(
                                f"[CHECKOUT] Input {idx}: name='{name}', id='{input_id}', placeholder='{placeholder}'"
                            )
                except Exception as e:
                    logger.debug(f"[CHECKOUT] Error logging inputs: {e}")

                # Fill visible form fields FIRST
                fields_filled = 0

                # Try to fill combined first and last name field (for matas.dk)
                for selector in settings.combined_name_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field and await field.is_visible():
                            current_value = await field.input_value()
                            if not current_value:
                                await field.fill(test_data["first_and_last_name"])
                                logger.info(f"[CHECKOUT] Filled combined name field: {selector}")
                                fields_filled += 1
                            break
                    except Exception as e:
                        logger.debug(f"[CHECKOUT] Combined name selector {selector} failed: {e}")

                # Try to fill email field
                for selector in settings.email_selectors:
                    try:
                        email_field = await page.query_selector(selector)
                        if email_field and await email_field.is_visible():
                            current_value = await email_field.input_value()
                            if not current_value:
                                await email_field.fill(test_data["email"])
                                logger.info(f"[CHECKOUT] Filled email: {selector}")
                                fields_filled += 1
                            break
                    except Exception as e:
                        logger.debug(f"[CHECKOUT] Email selector {selector} failed: {e}")

                # Try to fill first name
                for selector in settings.first_name_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field and await field.is_visible():
                            current_value = await field.input_value()
                            if not current_value:
                                await field.fill(test_data["first_name"])
                                logger.info(f"[CHECKOUT] Filled first name: {selector}")
                                fields_filled += 1
                            break
                    except Exception:
                        pass

                # Try to fill last name
                for selector in settings.last_name_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field and await field.is_visible():
                            current_value = await field.input_value()
                            if not current_value:
                                await field.fill(test_data["last_name"])
                                logger.info(f"[CHECKOUT] Filled last name: {selector}")
                                fields_filled += 1
                            break
                    except Exception:
                        pass

                # Try to fill phone
                for selector in settings.phone_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field and await field.is_visible():
                            current_value = await field.input_value()
                            if not current_value:
                                await field.fill(test_data["phone"])
                                logger.info(f"[CHECKOUT] Filled phone: {selector}")
                                fields_filled += 1
                            break
                    except Exception:
                        pass

                # Try to fill address
                for selector in settings.address_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field and await field.is_visible():
                            current_value = await field.input_value()
                            if not current_value:
                                await field.fill(test_data["address"])
                                logger.info(f"[CHECKOUT] Filled address: {selector}")
                                fields_filled += 1
                            break
                    except Exception:
                        pass

                # Try to fill postal code
                for selector in settings.postal_code_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field and await field.is_visible():
                            current_value = await field.input_value()
                            if not current_value:
                                await field.fill(test_data["postal_code"])
                                logger.info(f"[CHECKOUT] Filled postal code: {selector}")
                                fields_filled += 1
                            break
                    except Exception:
                        pass

                # Try to fill city
                for selector in settings.city_selectors:
                    try:
                        field = await page.query_selector(selector)
                        if field and await field.is_visible():
                            current_value = await field.input_value()
                            if not current_value:
                                await field.fill(test_data["city"])
                                logger.info(f"[CHECKOUT] Filled city: {selector}")
                                fields_filled += 1
                            break
                    except Exception:
                        pass

                logger.info(f"[CHECKOUT] Filled {fields_filled} fields at step {step + 1}")

                # Look for and click "Next", "Continue", "Næste" etc. buttons
                next_clicked = False
                for selector in settings.next_button_selectors:
                    try:
                        next_button = await page.query_selector(selector)
                        if next_button:
                            is_visible = await next_button.is_visible()
                            is_enabled = await next_button.is_enabled()
                            if is_visible and is_enabled:
                                button_text = await next_button.text_content()
                                logger.info(f"[CHECKOUT] Clicking '{button_text.strip()}' button: {selector}")
                                await next_button.click()
                                next_clicked = True
                                await asyncio.sleep(settings.checkout_step_wait)  # Wait for next step to load
                                break
                    except Exception as e:
                        logger.debug(f"[CHECKOUT] Next button selector {selector} failed: {e}")

                if next_clicked:
                    logger.info(f"[CHECKOUT] Progressed to next checkout step")

                    # After clicking next, check if shipping prices are now visible
                    await asyncio.sleep(settings.page_update_wait)  # Wait for page to update
                    
                    # Check for cookie popups after navigation to new step
                    await self._dismiss_cookie_banner_if_needed(page, context="CHECKOUT_STEP")
                    html = await page.content()
                    import re

                    shipping_prices_visible = any(
                        re.search(pattern, html.lower()) for pattern in settings.shipping_price_patterns
                    )

                    if shipping_prices_visible:
                        logger.info(f"[CHECKOUT] Shipping prices found after clicking Next at step {step + 1}!")
                        return
                    else:
                        logger.info(f"[CHECKOUT] Shipping prices not yet visible, will continue to next step...")
                        continue  # Continue to next iteration of the loop
                else:
                    logger.info(f"[CHECKOUT] No 'Next' button found")

                    # If no next button, check if shipping prices are visible on current page
                    html = await page.content()
                    import re

                    shipping_prices_visible = any(
                        re.search(pattern, html.lower()) for pattern in settings.shipping_price_patterns
                    )

                    if shipping_prices_visible and fields_filled > 0:
                        logger.info(
                            f"[CHECKOUT] No Next button but shipping prices visible on current page after filling {fields_filled} fields!"
                        )
                        return
                    elif fields_filled > 0:
                        logger.info(
                            f"[CHECKOUT] No Next button and no shipping prices visible yet. Filled {fields_filled} fields, continuing..."
                        )
                        continue
                    else:
                        # No next button and no fields filled - we're done
                        logger.info(f"[CHECKOUT] No more fields to fill or buttons to click")
                        break

            logger.info("[CHECKOUT] Completed checkout form processing")

        except Exception as e:
            logger.warning(f"[CHECKOUT] Error filling checkout details: {e}")

    async def _dismiss_cookie_banner_if_needed(self, page, context: str = "PAGE") -> bool:
        """Dismiss cookie consent banner if present. Checks dynamically on every call.
        
        Args:
            page: Playwright page object
            context: Context string for logging (e.g., 'PAGE', 'CART', 'CHECKOUT')
            
        Returns:
            True if cookie banner was dismissed, False otherwise
        """
        logger.debug(f"[{context}] Checking for cookie consent banner...")
        
        # Wait briefly for any dynamic cookie popups to appear
        await asyncio.sleep(0.5)
        
        for cookie_sel in settings.cookie_selectors:
            try:
                cookie_btn = await page.query_selector(cookie_sel)
                if cookie_btn:
                    is_visible = await cookie_btn.is_visible()
                    if is_visible:
                        await cookie_btn.click(timeout=1000)
                        logger.info(f"[{context}] ✓ Dismissed cookie banner: {cookie_sel}")
                        await asyncio.sleep(0.3)  # Brief wait after dismissal
                        return True
            except Exception as e:
                logger.debug(f"[{context}] Cookie selector {cookie_sel} failed: {e}")
                continue

        logger.debug(f"[{context}] No cookie banner found")
        return False

    async def _select_product_variant_if_needed(self, page) -> bool:
        """Select product size/variant if required before adding to cart."""
        logger.info("[CART] Checking for size/variant selectors...")
        for selector in settings.variant_selectors:
            try:
                variant_elements = await page.query_selector_all(selector)
                if variant_elements:
                    logger.info(f"[CART] Found {len(variant_elements)} size options with selector: {selector}")
                    for i, element in enumerate(variant_elements):
                        try:
                            is_visible = await element.is_visible()
                            if not is_visible:
                                logger.debug(f"[CART] Variant #{i} is hidden, skipping")
                                continue

                            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                            is_disabled = await element.is_disabled() if tag_name in ["button", "input"] else False

                            if tag_name == "select":
                                await element.select_option(index=1)
                                logger.info(f"[CART] Selected variant from visible dropdown (option 1)")
                                await asyncio.sleep(0.3)  # Brief wait after variant selection
                                await self._dismiss_cookie_banner_if_needed(page, context="VARIANT_SELECT")
                                return True
                            elif tag_name in ["button", "a"] and not is_disabled:
                                await element.click()
                                logger.info(f"[CART] Clicked visible variant {tag_name} #{i}")
                                await asyncio.sleep(0.3)  # Brief wait after variant selection
                                await self._dismiss_cookie_banner_if_needed(page, context="VARIANT_SELECT")
                                return True
                            elif tag_name == "label":
                                await element.click()
                                logger.info(f"[CART] Clicked variant label #{i}")
                                await asyncio.sleep(0.3)  # Brief wait after variant selection
                                await self._dismiss_cookie_banner_if_needed(page, context="VARIANT_SELECT")
                                return True
                            elif tag_name == "input" and not is_disabled:
                                await element.click()
                                logger.info(f"[CART] Clicked variant input #{i}")
                                await asyncio.sleep(0.3)  # Brief wait after variant selection
                                await self._dismiss_cookie_banner_if_needed(page, context="VARIANT_SELECT")
                                return True
                        except Exception as e:
                            logger.debug(f"[CART] Failed to select variant #{i}: {e}")
                            continue
                    if variant_elements:  # If we found elements, we tried to select one
                        return True
            except Exception as e:
                logger.debug(f"[CART] Variant selector {selector} failed: {e}")
                continue
        return False

    async def _find_add_to_cart_button(self, page):
        """Find and return the add-to-cart button using multiple strategies."""
        # Try JavaScript-based discovery first
        logger.info("[CART] Using JavaScript to find add-to-cart button...")
        add_to_cart_element = await page.evaluate(
            """() => {
            const cartTexts = ['læg i kurv', 'læg i indkøbskurven', 'tilføj til kurv', 'køb nu', 'add to cart', 'add to basket'];
            const elements = document.querySelectorAll('a.button, a.buy-button, button, input[type="submit"]');
            
            for (const el of elements) {
                const text = (el.textContent || el.value || '').toLowerCase().trim();
                if (text.length < 100 && cartTexts.some(ct => text.includes(ct))) {
                    return {
                        tag: el.tagName,
                        text: text,
                        class: el.className,
                        id: el.id,
                        href: el.href || null
                    };
                }
            }
            return null;
        }"""
        )

        cart_button = None
        if add_to_cart_element:
            logger.info(
                f"[CART] JavaScript found add-to-cart: tag={add_to_cart_element['tag']}, "
                f"text='{add_to_cart_element['text'][:50]}', class={add_to_cart_element['class']}"
            )

            try:
                if add_to_cart_element.get("href"):
                    selector = f"a[href='{add_to_cart_element['href']}']"
                elif add_to_cart_element.get("class"):
                    classes = add_to_cart_element["class"].split()
                    if len(classes) > 1:
                        selector = (
                            f"a.{classes[0]}.{classes[1]}"
                            if add_to_cart_element["tag"] == "A"
                            else f"button.{classes[0]}.{classes[1]}"
                        )
                    else:
                        selector = f"a.{classes[0]}" if add_to_cart_element["tag"] == "A" else f"button.{classes[0]}"
                elif add_to_cart_element.get("id"):
                    selector = f"#{add_to_cart_element['id']}"
                else:
                    selector = f"{add_to_cart_element['tag'].lower()}:has-text('{add_to_cart_element['text'][:15]}')"

                logger.info(f"[CART] Trying JavaScript-discovered selector: {selector}")
                cart_button = await page.query_selector(selector)
                if cart_button and await cart_button.is_visible() and await cart_button.is_enabled():
                    logger.info(f"[CART] Successfully found button with JS-discovered selector!")
                    return cart_button
            except Exception as e:
                logger.warning(f"[CART] Failed to find button using discovered selector: {e}")

        # Fallback to traditional selectors
        for selector in settings.add_to_cart_selectors:
            try:
                logger.info(f"[CART] Trying selector: {selector}")
                cart_button = await page.query_selector(selector)
                if cart_button:
                    is_visible = await cart_button.is_visible()
                    is_enabled = await cart_button.is_enabled()
                    logger.info(f"[CART] Found button with {selector}: visible={is_visible}, enabled={is_enabled}")

                    if is_visible and is_enabled:
                        logger.info(f"[CART] Using add-to-cart button: {selector}")
                        return cart_button
            except Exception as e:
                logger.debug(f"[CART] Selector {selector} failed: {e}")
                continue

        return None

    async def _click_add_to_cart_and_validate(self, page, cart_button) -> bool:
        """Click the add-to-cart button and validate the cart was updated."""
        try:
            url_before = page.url

            # Click without waiting for navigation
            try:
                await cart_button.click(timeout=5000, no_wait_after=True)
                logger.info("[CART] Clicked add-to-cart button")
            except Exception as click_error:
                logger.warning(f"[CART] Normal click failed: {click_error}, trying force click...")
                await cart_button.click(force=True, no_wait_after=True)
                logger.info("[CART] Force-clicked add-to-cart button")

            # Wait for cart to update
            await asyncio.sleep(settings.cart_modal_wait)
            
            # Check for cookie popups after add-to-cart action (might appear in modal)
            await self._dismiss_cookie_banner_if_needed(page, context="ADD_TO_CART")
            
            # Check for cookie popups after add-to-cart action (might appear in modal)
            await self._dismiss_cookie_banner_if_needed(page, context="ADD_TO_CART")

            # Validate using JavaScript
            cart_state = await page.evaluate(
                """() => {
                const indicators = {
                    cartCountElement: null,
                    cartCountValue: null,
                    cartModal: null,
                    checkoutButton: null
                };
                
                const countSelectors = ['[class*="cart-count"]', '[class*="cart-badge"]', '[class*="cart-quantity"]', '[class*="CartBadge"]', '[data-test*="cart-count"]'];
                for (const sel of countSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        indicators.cartCountElement = sel;
                        indicators.cartCountValue = el.textContent || el.innerText;
                        break;
                    }
                }
                
                const modalSelectors = ['[class*="cart-modal"]', '[class*="CartModal"]', '[class*="mini-cart"]', '[class*="MiniCart"]', '[class*="cart-drawer"]'];
                for (const sel of modalSelectors) {
                    const el = document.querySelector(sel);
                    if (el && (el.offsetParent !== null || window.getComputedStyle(el).display !== 'none')) {
                        indicators.cartModal = sel;
                        break;
                    }
                }
                
                const checkoutTexts = ['se kurv', 'gå til kurv', 'view cart', 'checkout', 'til kassen'];
                for (const text of checkoutTexts) {
                    const buttons = Array.from(document.querySelectorAll('button, a'));
                    const btn = buttons.find(b => b.textContent.toLowerCase().includes(text) && (b.offsetParent !== null));
                    if (btn) {
                        indicators.checkoutButton = text;
                        break;
                    }
                }
                
                return indicators;
            }"""
            )

            # Check JS indicators
            if cart_state:
                if cart_state.get("cartCountValue") and cart_state["cartCountValue"].strip() not in ["0", ""]:
                    logger.info(f"[CART] Validation passed (JS): Cart count shows {cart_state['cartCountValue']}")
                    return True
                elif cart_state.get("cartModal"):
                    logger.info(f"[CART] Validation passed (JS): Cart modal visible: {cart_state['cartModal']}")
                    return True
                elif cart_state.get("checkoutButton"):
                    logger.info(f"[CART] Validation passed (JS): Checkout button found: {cart_state['checkoutButton']}")
                    return True

            # Check URL change
            url_after = page.url
            if url_after != url_before:
                if any(
                    keyword in url_after.lower() for keyword in ["/cart", "/kurv", "/kassen", "/checkout", "/basket"]
                ):
                    logger.info(f"[CART] Validation passed: URL changed to cart/checkout: {url_after}")
                    return True

            # Check cart indicators
            for indicator in settings.cart_indicator_selectors:
                try:
                    element = await page.query_selector(indicator)
                    if element and await element.is_visible():
                        logger.info(f"[CART] Validation passed: Found cart indicator: {indicator}")
                        return True
                except Exception:
                    continue

            # Check cart quantity
            for indicator in settings.cart_quantity_selectors:
                try:
                    element = await page.query_selector(indicator)
                    if element:
                        text = await element.inner_text()
                        if text and text.strip() and text.strip() != "0":
                            logger.info(f"[CART] Validation passed: Cart quantity shows: {text}")
                            return True
                except Exception:
                    continue

            # Retry validation
            logger.warning("[CART] Failed initial validation - retrying...")
            await asyncio.sleep(settings.validation_retry_wait)
            for indicator in settings.cart_indicator_selectors:
                try:
                    element = await page.query_selector(indicator)
                    if element and await element.is_visible():
                        logger.info(f"[CART] Validation passed (retry): Found cart indicator: {indicator}")
                        return True
                except Exception:
                    continue

            logger.warning("[CART] Cart validation failed - cart might be empty")
            return False

        except Exception as e:
            logger.warning(f"[CART] Failed to click add-to-cart: {e}")
            return False

    async def _navigate_to_checkout_page(self, page) -> bool:
        """Navigate directly to checkout page."""
        try:
            current_url = page.url
            from urllib.parse import urlparse, urljoin

            parsed = urlparse(current_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            checkout_urls = [
                urljoin(base_url, "/checkout"),
                urljoin(base_url, "/kassen"),
                urljoin(base_url, "/levering"),
            ]

            for checkout_url in checkout_urls:
                try:
                    logger.info(f"[CART] Attempting to navigate directly to: {checkout_url}")
                    await page.goto(checkout_url, wait_until="domcontentloaded", timeout=settings.navigation_timeout)
                    await asyncio.sleep(settings.page_update_wait)
                    
                    # Check for cookie popups after navigation
                    await self._dismiss_cookie_banner_if_needed(page, context="CHECKOUT_NAV")
                    
                    current = page.url.lower()
                    if any(keyword in current for keyword in ["/checkout", "/kassen", "/levering"]):
                        logger.info(f"[CART] Successfully navigated to checkout: {page.url}")
                        return True
                except Exception as nav_error:
                    logger.debug(f"[CART] Failed to navigate to {checkout_url}: {nav_error}")
                    continue

            # Try cart URLs
            cart_urls = [urljoin(base_url, "/cart"), urljoin(base_url, "/kurv")]
            for cart_url in cart_urls:
                try:
                    logger.info(f"[CART] Attempting to navigate to cart: {cart_url}")
                    await page.goto(cart_url, wait_until="domcontentloaded", timeout=settings.navigation_timeout)
                    await asyncio.sleep(settings.page_update_wait)
                    
                    # Check for cookie popups after navigation
                    await self._dismiss_cookie_banner_if_needed(page, context="CART_PAGE")
                    
                    current = page.url.lower()
                    if any(keyword in current for keyword in ["/cart", "/kurv"]):
                        logger.info(f"[CART] Successfully navigated to cart: {page.url}")
                        return True
                except Exception as nav_error:
                    logger.debug(f"[CART] Failed to navigate to {cart_url}: {nav_error}")
                    continue

            return False
        except Exception as e:
            logger.warning(f"[CART] Failed to navigate to checkout: {e}")
            return False

    async def _extract_shipping_from_cart(self, page, soup: BeautifulSoup) -> List[ShippingProvider]:
        """
        Extract shipping information by adding product to cart and checking checkout.
        More accurate than page-based extraction.
        Works on product pages - adds item to cart and proceeds to checkout.
        """
        providers = []
        try:
            logger.info("[CART] Attempting to extract shipping from cart/checkout...")

            # Step 1: Dismiss cookie banner if needed
            await self._dismiss_cookie_banner_if_needed(page, context="CART")

            # Step 2: Select product variant if needed
            variant_selected = await self._select_product_variant_if_needed(page)
            if variant_selected:
                logger.info("[CART] Waiting for add-to-cart button to become enabled after variant selection...")
                await asyncio.sleep(settings.variant_select_wait)

            # Step 3: Find add-to-cart button
            cart_button = await self._find_add_to_cart_button(page)
            if not cart_button:
                logger.info("[CART] No add-to-cart button found, skipping cart extraction")
                return []

            # Step 4: Click add-to-cart and validate
            cart_validated = await self._click_add_to_cart_and_validate(page, cart_button)
            if not cart_validated:
                logger.warning("[CART] Cart validation failed, attempting direct navigation to checkout...")
                navigated = await self._navigate_to_checkout_page(page)
                if not navigated:
                    logger.warning("[CART] Failed to navigate to checkout - skipping shipping extraction")
                    return []

            # Look for cart/checkout button (both in modal and on page)
            checkout_link = None
            for selector in settings.checkout_selectors:
                try:
                    checkout_link = await page.query_selector(selector)
                    if checkout_link:
                        is_visible = await checkout_link.is_visible()
                        if is_visible:
                            logger.info(f"[CART] Found checkout link: {selector}")
                            break
                        else:
                            checkout_link = None
                except Exception:
                    continue

            # Check if we're already on a checkout page (after direct navigation)
            current_url = page.url.lower()
            already_on_checkout = any(keyword in current_url for keyword in ["/checkout", "/kassen", "/levering"])

            if already_on_checkout and not checkout_link:
                logger.info(f"[CART] Already on checkout page: {page.url}, proceeding to fill forms...")
                checkout_success = True
                # Try to fill checkout details
                await self._fill_checkout_details_if_needed(page)

            # After adding to cart, navigate directly to the appropriate checkout page based on domain
            elif checkout_link or True:  # Always try direct navigation after adding to cart
                try:
                    logger.info(f"[CART] Waiting for cart to update...")
                    await asyncio.sleep(settings.cart_modal_wait)  # Wait for cart to update with added item

                    # Get the base URL from current page
                    current_url = page.url
                    from urllib.parse import urlparse

                    parsed = urlparse(current_url)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    domain = parsed.netloc.lower()

                    # Determine the correct checkout page based on domain
                    checkout_path = None
                    if "matas" in domain:
                        checkout_path = "/levering"  # matas.dk uses /levering for delivery/checkout
                        logger.info("[CART] Detected matas.dk - will navigate to /levering")
                    elif "jollyroom" in domain:
                        checkout_path = "/kassen"  # jollyroom.dk uses /kassen for checkout
                        logger.info("[CART] Detected jollyroom.dk - will navigate to /kassen")
                    elif "brudsikreglas" in domain:
                        checkout_path = "/checkout/"  # brudsikreglas.dk uses /checkout/
                        logger.info("[CART] Detected brudsikreglas.dk - will navigate to /checkout/")
                    else:
                        # Generic fallback - try common checkout paths
                        checkout_path = "/checkout"
                        logger.info(f"[CART] Unknown domain, trying generic /checkout")

                    # Build the full checkout URL
                    checkout_url = f"{base_url}{checkout_path}"

                    logger.info(f"[CART] Navigating directly to checkout page: {checkout_url}")
                    await page.goto(checkout_url, wait_until="domcontentloaded", timeout=settings.page_timeout)
                    await asyncio.sleep(settings.page_update_wait)
                    checkout_success = True
                    logger.info(f"[CART] Successfully navigated to: {page.url}")
                    
                    # Check for cookie popups after navigation
                    await self._dismiss_cookie_banner_if_needed(page, context="CHECKOUT_NAV")

                    # Now we're on the checkout page with the added item in basket
                    # Proceed directly to fill checkout details
                    await self._fill_checkout_details_if_needed(page)

                except Exception as e:
                    logger.warning(f"[CART] Error during checkout navigation: {e}")
                    logger.info(f"[CART] Will extract from current page/modal")
            else:
                # No checkout link found - might be on cart page
                # Try to look for checkout button and navigate, or try filling forms if already on checkout
                logger.info("[CART] No checkout link found")
                current_page_url = page.url.lower()

                # If on cart page, try to find and click checkout button
                if any(keyword in current_page_url for keyword in ["/cart", "/kurv", "/basket"]):
                    logger.info("[CART] On cart page, looking for checkout button to proceed...")
                    # Try button selectors (not just links)
                    checkout_button = None
                    for btn_sel in settings.checkout_button_selectors:
                        try:
                            checkout_button = await page.query_selector(btn_sel)
                            if checkout_button and await checkout_button.is_visible():
                                logger.info(f"[CART] Found checkout button: {btn_sel}")
                                await checkout_button.click()
                                await asyncio.sleep(settings.checkout_step_wait)
                                logger.info(f"[CART] Clicked checkout button, now at: {page.url}")
                                
                                # Check for cookie popups after clicking checkout button
                                await self._dismiss_cookie_banner_if_needed(page, context="CHECKOUT_BUTTON")
                                
                                # Fill checkout details after navigating
                                await self._fill_checkout_details_if_needed(page)
                                checkout_success = True
                                break
                        except Exception as btn_err:
                            logger.debug(f"[CART] Button {btn_sel} failed: {btn_err}")
                            continue

                    if not checkout_button:
                        logger.warning("[CART] Could not find checkout button on cart page")
                else:
                    # Might already be on checkout, try filling forms
                    logger.info(f"[CART] Not on cart page, attempting to fill checkout forms at: {page.url}")
                    await self._fill_checkout_details_if_needed(page)

            # Extract shipping options from cart/checkout page
            try:
                # First, try to expand any collapsed shipping sections/cards
                await self._expand_shipping_sections(page)

                html_content = await page.content()
                cart_soup = BeautifulSoup(html_content, "html.parser")
            except Exception as e:
                logger.warning(f"[CART] Failed to get page content: {e}")
                return []

            # Look for shipping options in checkout
            shipping_sections = []

            # Strategy 1: Find individual shipping option cards/containers
            # Look for elements that likely represent individual shipping options
            card_selectors = [
                {
                    "class": lambda x: x
                    and any(
                        k in " ".join(x).lower()
                        for k in ["shipping-option", "delivery-option", "shipping-card", "delivery-method", "shipping-rate"]
                    )
                },
                {"class": lambda x: x and "radio" in " ".join(x).lower() and "label" in " ".join(x).lower()},
            ]

            for selector in card_selectors:
                cards = cart_soup.find_all(["div", "li", "label", "tr"], attrs=selector)
                shipping_sections.extend(cards)

            # Strategy 2: Find shipping method radio buttons and their labels
            shipping_radios = cart_soup.find_all(
                "input",
                attrs={
                    "type": "radio",
                    "name": lambda x: x and ("shipping" in x.lower() or "levering" in x.lower() or "delivery" in x.lower()) if x else False,
                },
            )
            for radio in shipping_radios:
                # Get the label associated with this radio button
                radio_id = radio.get("id")
                if radio_id:
                    label = cart_soup.find("label", attrs={"for": radio_id})
                    if label:
                        shipping_sections.append(label)
                # Also check parent container (but only immediate parent)
                if radio.parent and radio.parent.name in ["div", "li", "label", "td"]:
                    shipping_sections.append(radio.parent)

            # Strategy 3: Find by class/id keywords (but filter out large containers)
            for keyword in [
                "shipping",
                "delivery",
                "levering",
                "forsendelse",
                "fragt",
                "shipping_method",
                "shipping-method",
                "delivery-method",
                "leveringsmetode",
            ]:
                sections = cart_soup.find_all(class_=lambda x: x and keyword in x.lower() if x else False)
                # Filter: only add if the section is relatively small (not a large container)
                for section in sections:
                    text_len = len(section.get_text(strip=True))
                    # Skip if text is too long (likely a container) or too short
                    if 20 < text_len < 800:  # Increased max to capture more complete shipping info
                        shipping_sections.append(section)

            # Strategy 4: Find table rows that contain shipping information
            # Many checkout pages use tables to display shipping options
            table_rows = cart_soup.find_all("tr")
            for row in table_rows:
                row_text = row.get_text(strip=True).lower()
                if any(keyword in row_text for keyword in ["shipping", "levering", "forsendelse", "delivery", "fragt"]):
                    # Make sure it's not a header row
                    if not row.find("th"):
                        shipping_sections.append(row)

            # Remove duplicates while preserving order
            seen = set()
            unique_sections = []
            for section in shipping_sections:
                section_str = str(section)[:100]  # Use first 100 chars as identifier
                if section_str not in seen:
                    seen.add(section_str)
                    unique_sections.append(section)
            shipping_sections = unique_sections

            logger.info(f"[CART] Found {len(shipping_sections)} potential shipping sections")
            
            # Debug: Log sample of what we found to help diagnose issues
            if shipping_sections:
                logger.info(f"[CART] Sample of shipping sections found:")
                for idx, section in enumerate(shipping_sections[:3]):
                    sample_text = section.get_text(strip=True)[:150]
                    logger.info(f"  Section {idx + 1}: {sample_text}...")
            else:
                logger.warning(f"[CART] WARNING: No shipping sections found!")
                logger.warning(f"[CART] This could mean:")
                logger.warning(f"  1. Checkout page doesn't have shipping options visible")
                logger.warning(f"  2. Need to expand collapsed sections or complete more checkout steps")
                logger.warning(f"  3. Selectors need adjustment for this specific site")
                logger.info(f"[CART] Current page URL: {page.url}")

            # Extract shipping providers from checkout sections
            seen_providers = set()
            for section in shipping_sections:
                text = section.get_text(separator=" ", strip=True)
                text_lower = text.lower()

                logger.info(f"[CART] Analyzing shipping option: {text[:200]}...")

                # Skip product variations and non-shipping content
                skip_keywords = [
                    "choose an option",
                    "vælg",
                    "se priser",
                    "varenummer",
                    "antal",
                    "quantity",
                    "tilføj til",
                    "add to",
                    "læg i kurv",
                    "product",
                    "produkt",
                    "stk.",
                    "v/300",
                    "v/200",
                    "v/150",
                ]
                if any(keyword in text_lower for keyword in skip_keywords):
                    logger.info(f"[CART] Skipping - appears to be product variation, not shipping")
                    continue

                # Skip if this looks like it's not shipping-related at all
                if not self._is_shipping_related(text_lower):
                    logger.debug(f"[CART] Skipping - not shipping-related")
                    continue

                # Extract provider name with multiple strategies
                provider_name = None
                providers_list = []  # To handle multiple providers in one section (e.g., "GLS, DAO eller PostNord")

                # Strategy 1: Check for known provider keywords (cart extraction)
                # Order matters - check most specific first
                known_providers = {
                    "burd express": "Burd Express",  # Check multi-word first
                    "post nord": "PostNord",
                    "postnord": "PostNord",
                    "pakkeshop": "PostNord Pakkeshop",
                    "pakkeboks": "PostNord Pakkeboks",
                    "gls": "GLS",
                    "dao": "DAO",  # Danish delivery service
                    "bring": "Bring",
                    "burd": "Burd",  # Burd Express
                    "dhl": "DHL",
                    "ups": "UPS",
                    "fedex": "FedEx",
                    "dpd": "DPD",
                    "pdk": "PDK",
                    "swipbox": "Swipbox",
                    "budbee": "Budbee",
                    "packeta": "Packeta",
                    "matas": "Matas",  # Matas butik (in-store pickup)
                }

                import re

                # Find ALL providers in the text (e.g., "GLS, DAO eller PostNord" should find all three)
                for keyword, name in known_providers.items():
                    # Use word boundary matching to avoid false positives
                    pattern = r"\b" + re.escape(keyword) + r"\b"
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        if name not in providers_list:
                            providers_list.append(name)
                            logger.info(f"[CART] Detected provider: {name}")

                # If we found multiple providers, use the combined name or take the primary one
                if len(providers_list) > 1:
                    provider_name = " / ".join(providers_list)  # e.g., "GLS / DAO / PostNord"
                elif len(providers_list) == 1:
                    provider_name = providers_list[0]

                # Strategy 2: Extract from common patterns
                if not provider_name:
                    import re

                    patterns = [
                        r"(?:levering|forsendelse|fragt)\s+(?:med|via|by)\s+([A-Z][A-Za-z]+)",
                        r"([A-Z][A-Za-z]+)\s+(?:levering|forsendelse|delivery|shipping)",
                        r"(?:via|by)\s+([A-Z][A-Za-z]+)",
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            potential_name = match.group(1)
                            if potential_name.lower() not in [
                                "levering",
                                "delivery",
                                "shipping",
                                "standard",
                                "express",
                                "hurtig",
                                "normal",
                            ]:
                                provider_name = potential_name
                                logger.info(f"[CART] Extracted provider from pattern: {provider_name}")
                                break

                # Extract price - use improved method that filters out non-shipping costs
                cost, currency = self._extract_shipping_cost_from_text(text, text_lower)

                # Extract delivery time
                delivery_time = self.data_extractor.extract_delivery_time_with_regex(text)

                # Classify delivery type based on text content
                delivery_type = self._classify_delivery_type(text_lower)

                # Only add if we have actual price information (including 0.0 for free shipping)
                # Don't add providers without price info - they're incomplete
                if cost is not None:
                    final_name = provider_name or ("Free Shipping" if cost == 0.0 else "Standard Shipping")

                    # Deduplicate based on name, cost, and delivery type (not delivery_time to avoid splitting same option)
                    provider_key = f"{final_name}_{cost}_{delivery_type}"
                    if provider_key in seen_providers:
                        logger.debug(f"[CART] Skipping duplicate provider: {provider_key}")
                        continue
                    seen_providers.add(provider_key)

                    providers.append(
                        ShippingProvider(
                            name=final_name,
                            price=cost,
                            currency=currency,
                            delivery_time=delivery_time or "Unknown",
                            delivery_type=delivery_type,
                            description=text[:200] if len(text) > 200 else text,
                        )
                    )
                    logger.info(
                        f"[CART] Extracted shipping: {final_name}, {cost} {currency if cost is not None else 'TBD'}, Time: {delivery_time or 'Unknown'}, Type: {delivery_type}"
                    )
                else:
                    # Skip providers without price - they're incomplete information
                    if provider_name:
                        logger.debug(f"[CART] Skipping {provider_name} - no price information found")

            if providers:
                logger.info(f"[CART] Successfully extracted {len(providers)} shipping provider(s) from cart/checkout")
                # Log what we're actually returning
                logger.info(f"[CART] Final provider list being returned:")
                for idx, p in enumerate(providers, 1):
                    logger.info(f"  {idx}. {p.name}: {p.price} {p.currency}, {p.delivery_time}, {p.delivery_type}")
            else:
                logger.warning("[CART] No shipping providers found in cart/checkout")
                logger.info("[CART] Attempting fallback: searching entire page for shipping info...")
                
                # Fallback: Search entire page more broadly
                fallback_providers = await self._extract_shipping_fallback(page, cart_soup)
                if fallback_providers:
                    providers.extend(fallback_providers)
                    logger.info(f"[CART] Fallback found {len(fallback_providers)} provider(s)")

        except Exception as e:
            logger.warning(f"[CART] Error extracting shipping from cart: {e}")
            logger.debug(f"[CART] Traceback: {traceback.format_exc()}")

        return providers

    async def _extract_shipping_fallback(self, page, soup: BeautifulSoup) -> List[ShippingProvider]:
        """
        Fallback method to extract shipping when standard methods fail.
        Uses more aggressive text searching across the entire page.
        
        Args:
            page: Playwright page object
            soup: BeautifulSoup of page content
            
        Returns:
            List of ShippingProvider objects
        """
        providers = []
        seen_providers = set()
        
        try:
            logger.info("[CART FALLBACK] Searching entire page for shipping information...")
            
            # Strategy: Find all text containing shipping-related keywords
            all_text_elements = soup.find_all(text=lambda t: t and len(t.strip()) > 10)
            
            shipping_texts = []
            for text_elem in all_text_elements:
                text = text_elem.strip()
                text_lower = text.lower()
                
                # Check if contains shipping keywords
                if any(k in text_lower for k in ["levering", "delivery", "shipping", "forsendelse", "fragt"]):
                    # Also has a price or provider name
                    has_price = any(c.isdigit() for c in text)
                    has_provider = any(p in text_lower for p in ["gls", "postnord", "dao", "bring", "dhl"])
                    
                    if has_price or has_provider:
                        parent = text_elem.parent
                        if parent and parent.name not in ["script", "style"]:
                            # Get parent context
                            context = parent.get_text(strip=True)
                            if len(context) < 500:  # Not too large
                                shipping_texts.append(context)
            
            # Deduplicate
            unique_texts = list(set(shipping_texts))
            logger.info(f"[CART FALLBACK] Found {len(unique_texts)} unique text segments with shipping info")
            
            # Extract from each unique text
            for text in unique_texts[:20]:  # Limit to prevent too many
                text_lower = text.lower()
                
                if not self._is_shipping_related(text_lower):
                    continue
                
                # Extract provider name
                provider_name = None
                known_providers = {
                    "burd express": "Burd Express",
                    "post nord": "PostNord",
                    "postnord": "PostNord",
                    "pakkeshop": "PostNord Pakkeshop",
                    "pakkeboks": "PostNord Pakkeboks",
                    "gls": "GLS",
                    "dao": "DAO",
                    "bring": "Bring",
                    "burd": "Burd",
                    "dhl": "DHL",
                    "ups": "UPS",
                    "fedex": "FedEx",
                }
                
                import re
                for keyword, name in known_providers.items():
                    pattern = r"\b" + re.escape(keyword) + r"\b"
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        provider_name = name
                        break
                
                # Extract cost and delivery time
                cost, currency = self._extract_shipping_cost_from_text(text, text_lower)
                delivery_time = self.data_extractor.extract_delivery_time_with_regex(text)
                delivery_type = self._classify_delivery_type(text_lower)
                
                # Add if we have something useful
                if provider_name or cost is not None:
                    final_name = provider_name or ("Free Shipping" if cost == 0.0 else "Standard Shipping")
                    
                    provider_key = f"{final_name}_{cost}_{delivery_time}_{delivery_type}"
                    if provider_key not in seen_providers:
                        seen_providers.add(provider_key)
                        
                        providers.append(
                            ShippingProvider(
                                name=final_name,
                                price=cost,
                                currency=currency if cost is not None else None,
                                delivery_time=delivery_time or "Unknown",
                                delivery_type=delivery_type,
                                description=text[:200] if len(text) > 200 else text,
                            )
                        )
                        logger.info(f"[CART FALLBACK] Extracted: {final_name}, {cost} {currency if cost else 'TBD'}")
            
            return providers
            
        except Exception as e:
            logger.warning(f"[CART FALLBACK] Error in fallback extraction: {e}")
            return []

    def _is_shipping_related(self, text_lower: str) -> bool:
        """
        Check if text is actually related to shipping/delivery.
        
        Args:
            text_lower: Lowercase text to check
            
        Returns:
            True if shipping-related, False otherwise
        """
        shipping_indicators = [
            "shipping", "delivery", "levering", "forsendelse", "fragt",
            "postnord", "gls", "dao", "dhl", "ups", "fedex", "bring",
            "pakkeshop", "pakkeboks", "hjemlevering", "home delivery",
            "express", "standard", "gratis", "free"
        ]
        
        return any(indicator in text_lower for indicator in shipping_indicators)

    def _extract_shipping_cost_from_text(self, text: str, text_lower: str) -> tuple[Optional[float], Optional[str]]:
        """
        Extract shipping cost from text, filtering out non-shipping costs.
        
        Filters out:
        - Product prices (usually higher than shipping)
        - Tax amounts
        - Order totals
        - Minimum order values
        - Delivery time numbers (e.g., "2-4 days")
        
        Args:
            text: Original text
            text_lower: Lowercase version of text
            
        Returns:
            Tuple of (cost, currency) or (None, None)
        """
        import re
        
        # Check for free shipping first
        is_free = any(word in text_lower for word in ["gratis", "free", "fri levering", "fri fragt"])
        if is_free:
            logger.info(f"[CART] Free shipping detected")
            return 0.0, "DKK"
        
        # IMPORTANT: Check if this text is primarily about delivery time, not price
        # This prevents extracting "2" from "2-4 arbejdsdage" as a price
        delivery_time_only_patterns = [
            r"leveringstiden\s+tager\s+normalt\s+\d+[-–]\d+\s+(?:arbejdsdage|hverdage|dage)",  # "leveringstiden tager normalt 2-4 arbejdsdage"
            r"^\s*\d+[-–]\d+\s+(?:arbejdsdage|hverdage|dage|business\s*days?|days?)\s*$",  # Just "2-4 arbejdsdage"
            r"leveres\s+(?:inden\s+)?(?:for\s+)?\d+[-–]\d+\s+(?:arbejdsdage|hverdage|dage)",  # "leveres inden 2-4 dage"
        ]
        
        for pattern in delivery_time_only_patterns:
            if re.search(pattern, text_lower):
                # Check if there's also a price in the text (like "...2-4 arbejdsdage. 79 kr")
                # If yes, don't skip - extract the price
                if re.search(r"\d+\s*kr", text_lower):
                    logger.info(f"[CART] Text has delivery time AND price, will try to extract price")
                    break  # Don't return None, continue to price extraction
                else:
                    logger.debug(f"[CART] Text is about delivery time only, not price: {text[:50]}")
                    return None, None
        
        # Check for "Fra X kr" (from X kr) - minimum price
        fra_match = re.search(r"fra\s+(\d+[.,]?\d*)\s*kr", text_lower)
        if fra_match:
            cost = float(fra_match.group(1).replace(",", "."))
            logger.info(f"[CART] Found minimum shipping price: Fra {cost} DKK")
            return cost, "DKK"
        
        # Extract all prices from the text
        all_prices = []
        
        # Pattern 1: Look for explicit shipping price indicators
        explicit_patterns = [
            r"(?:shipping|levering|forsendelse|fragt)[:\s]+(\d+[.,]?\d*)\s*(?:kr|dkk)",
            r"(\d+[.,]?\d*)\s*(?:kr|dkk)\s*(?:shipping|levering|forsendelse|fragt)",
            r"(?:pris|price|cost)[:\s]+(\d+[.,]?\d*)\s*(?:kr|dkk)",
        ]
        
        for pattern in explicit_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                try:
                    price = float(match.group(1).replace(",", "."))
                    all_prices.append((price, "DKK", "explicit"))
                    logger.debug(f"[CART] Found explicit shipping price: {price} DKK")
                except (ValueError, IndexError):
                    continue
        
        # If we found explicit shipping prices, use the first one
        if all_prices:
            cost, currency, _ = all_prices[0]
            return cost, currency
        
        # Pattern 2: Look for standalone price (e.g., "59 kr") BUT ensure it's not part of delivery time
        # Ensure the number is followed by "kr" or currency, not by "arbejdsdage" or similar
        standalone_price_pattern = r"(\d+[.,]?\d*)\s*(?:kr|dkk)(?!\s*[-–]|\s*arbejdsdage|\s*hverdage|\s*dage|\s*days)"
        matches = list(re.finditer(standalone_price_pattern, text_lower))
        
        logger.debug(f"[CART] Standalone price pattern found {len(matches)} matches in text: {text[:100]}")
        
        if matches:
            # Get all potential prices
            potential_prices = []
            for match in matches:
                try:
                    price = float(match.group(1).replace(",", "."))
                    
                    # Check the context BEFORE the price (not after) - this is key!
                    # If "arbejdsdage" etc. appears BEFORE the price number, it might be delivery time
                    # But if it appears after (like "2-4 arbejdsdage. 79 kr"), the price is separate
                    start = max(0, match.start() - 15)  # Reduced from 30 to 15
                    before_context = text_lower[start:match.start()]
                    
                    logger.debug(f"[CART] Checking price {price}, before_context: '{before_context}'")
                    
                    # Skip only if the number itself is part of a delivery time range (e.g., "2-4")
                    # Check if there's a dash right before our number
                    if re.search(r"\d+\s*[-–]\s*$", before_context):
                        logger.debug(f"[CART] Skipping {price} - part of range like '2-4'")
                        continue
                    
                    # Skip if this looks like "2 kr arbejdsdage" (price directly followed by time unit)
                    after_start = match.end()
                    after_end = min(len(text_lower), match.end() + 20)
                    after_context = text_lower[after_start:after_end]
                    
                    if re.match(r"^\s*[-–]?\s*\d+\s*(?:arbejdsdage|hverdage|dage|days)", after_context):
                        logger.debug(f"[CART] Skipping {price} - followed by delivery time")
                        continue
                    
                    potential_prices.append(price)
                except (ValueError, IndexError):
                    continue
            
            logger.debug(f"[CART] After filtering, {len(potential_prices)} potential prices remain")
            
            # Use the first valid price found
            if potential_prices:
                cost = potential_prices[0]
                if self._is_valid_shipping_cost(cost, text_lower):
                    logger.info(f"[CART] Found shipping price: {cost} DKK")
                    return cost, "DKK"
                else:
                    logger.debug(f"[CART] Price {cost} failed validation")
        
        # Pattern 3: Try standard price extraction but validate more strictly
        price_match = self.data_extractor.extract_price_with_regex(text)
        if price_match:
            cost, currency = price_match
            
            # Additional validation: check if the price appears near delivery time indicators
            # Find the position of the price in the text
            price_str = str(int(cost)) if cost == int(cost) else str(cost).replace(".", ",")
            price_pos = text_lower.find(price_str)
            
            if price_pos >= 0:
                # Check 50 chars before and after
                context_start = max(0, price_pos - 50)
                context_end = min(len(text_lower), price_pos + 50)
                context = text_lower[context_start:context_end]
                
                # If delivery time keywords are very close to the number, it's likely delivery time
                if re.search(r"\d+[-–]\d+\s*(?:arbejdsdage|hverdage|dage|days)", context):
                    logger.debug(f"[CART] Rejected {cost} - too close to delivery time indicators")
                    return None, None
            
            # Validate: shipping costs are typically between 0 and 200 DKK
            if self._is_valid_shipping_cost(cost, text_lower):
                logger.info(f"[CART] Found shipping price: {cost} {currency}")
                return cost, currency
            else:
                logger.debug(f"[CART] Rejected price {cost} - doesn't appear to be shipping cost")
                return None, None
        
        return None, None

    def _is_valid_shipping_cost(self, cost: float, text_lower: str) -> bool:
        """
        Validate if a price is likely a shipping cost.
        
        Args:
            cost: The price amount
            text_lower: Lowercase text context
            
        Returns:
            True if likely a shipping cost, False otherwise
        """
        # Shipping costs are typically between 0 and 200 DKK in Denmark
        # Anything outside this range is likely not shipping
        if cost < 0 or cost > 250:
            logger.debug(f"[CART] Cost {cost} outside normal shipping range")
            return False
        
        # Exclude if text mentions these non-shipping indicators
        exclude_indicators = [
            "total", "sum", "subtotal", "i alt", "beløb",
            "minimum", "mindste", "køb for",  # minimum order value
            "moms", "tax", "vat", "skat",  # tax
            "rabat", "discount", "besparelse",  # discount
            "product", "produkt", "vare",  # product price
        ]
        
        if any(indicator in text_lower for indicator in exclude_indicators):
            logger.debug(f"[CART] Text contains non-shipping indicator")
            return False
        
        return True

    async def _extract_shipping_providers(self, soup: BeautifulSoup) -> List[ShippingProvider]:
        """
        Extract shipping provider information from product page.
        Uses improved logic to find all shipping options and filter out non-shipping costs.
        """
        providers = []
        try:
            # Common shipping provider keywords
            shipping_keywords = [
                "levering",
                "delivery",
                "shipping",
                "forsendelse",
                "fragt",
                "dhl",
                "postnord",
                "gls",
                "dao",
                "ups",
                "fedex",
                "bring",
                "gratis",
                "free",
                "fri",
            ]

            # Search for shipping information in common locations
            shipping_sections = []

            # Look for shipping/delivery divs and spans, but exclude script and style tags
            for keyword in ["delivery", "shipping", "levering", "forsendelse", "fragt"]:
                # Find elements with shipping-related classes, but not in script/style
                sections = soup.find_all(class_=lambda x: x and keyword in x.lower() if x else False)
                for section in sections:
                    # Skip if it's inside a script or style tag
                    if section.find_parent(["script", "style"]):
                        continue
                    shipping_sections.append(section)

                # Also check for spans/divs with shipping text, but exclude script/style
                text_sections = soup.find_all(text=lambda t: t and keyword in t.lower() if t else False)
                for ts in text_sections:
                    if ts.parent and not ts.find_parent(["script", "style"]):
                        shipping_sections.append(ts.parent)

            # Deduplicate sections
            unique_sections = []
            seen_texts = set()
            for section in shipping_sections:
                text = section.get_text(strip=True)
                if text and text not in seen_texts and len(text) > 10:  # Skip very short text
                    unique_sections.append(section)
                    seen_texts.add(text)

            logger.info(f"[SHIPPING] Found {len(unique_sections)} unique shipping sections on page")

            # Track seen providers to avoid duplicates
            seen_providers = set()

            # Look for shipping info in text - analyze ALL unique sections, not just first 5
            for idx, section in enumerate(unique_sections):
                text = section.get_text(strip=True)
                text_lower = text.lower()

                logger.info(f"[SHIPPING] Analyzing section {idx + 1}/{len(unique_sections)}: {text[:150]}...")

                # Check if this section actually contains useful shipping info
                if not self._is_shipping_related(text_lower):
                    logger.debug(f"[SHIPPING] Skipping - not shipping-related")
                    continue

                # Skip if text is too long (likely a large container with multiple items)
                if len(text) > 1000:
                    logger.debug(f"[SHIPPING] Skipping - text too long ({len(text)} chars), likely container")
                    continue

                # Extract provider name with multiple strategies
                provider_name = None
                providers_list = []

                # Strategy 1: Check for known provider keywords
                known_providers = {
                    "burd express": "Burd Express",
                    "post nord": "PostNord",
                    "postnord": "PostNord",
                    "pakkeshop": "PostNord Pakkeshop",
                    "pakkeboks": "PostNord Pakkeboks",
                    "gls": "GLS",
                    "dao": "DAO",
                    "bring": "Bring",
                    "burd": "Burd",
                    "dhl": "DHL",
                    "ups": "UPS",
                    "fedex": "FedEx",
                    "dpd": "DPD",
                    "pdk": "PDK",
                    "swipbox": "Swipbox",
                    "budbee": "Budbee",
                    "packeta": "Packeta",
                }

                import re

                # Find ALL providers mentioned in the text
                for keyword, name in known_providers.items():
                    pattern = r"\b" + re.escape(keyword) + r"\b"
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        if name not in providers_list:
                            providers_list.append(name)
                            logger.info(f"[SHIPPING] Detected provider: {name}")

                # Use all found providers or combine them
                if len(providers_list) > 1:
                    provider_name = " / ".join(providers_list)
                elif len(providers_list) == 1:
                    provider_name = providers_list[0]

                # Strategy 2: Extract from common patterns
                if not provider_name:
                    patterns = [
                        r"(?:levering|forsendelse|fragt)\s+(?:med|via|by)\s+([A-Z][A-Za-z]+)",
                        r"([A-Z][A-Za-z]+)\s+(?:levering|forsendelse|delivery|shipping)",
                        r"(?:via|by)\s+([A-Z][A-Za-z]+)",
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            potential_name = match.group(1)
                            if potential_name.lower() not in [
                                "levering",
                                "delivery",
                                "shipping",
                                "standard",
                                "express",
                                "hurtig",
                                "normal",
                            ]:
                                provider_name = potential_name
                                logger.info(f"[SHIPPING] Extracted provider from pattern: {provider_name}")
                                break

                # Check for free shipping
                is_free = any(word in text_lower for word in ["gratis", "free", "fri levering", "fri fragt"])

                # Extract delivery time
                delivery_time = self.data_extractor.extract_delivery_time_with_regex(text)
                if delivery_time:
                    logger.info(f"[SHIPPING] Detected delivery time: {delivery_time}")

                # Extract cost using improved method
                cost, currency = self._extract_shipping_cost_from_text(text, text_lower)

                # Classify delivery type based on text content
                delivery_type = self._classify_delivery_type(text_lower)

                # Determine if we should add this provider
                has_confident_info = (
                    provider_name or  # Named provider
                    cost is not None or  # Has cost (including 0 for free)
                    (delivery_time and any(k in text_lower for k in ["levering", "delivery", "shipping", "forsendelse"]))  # Has delivery time and shipping mention
                )

                if has_confident_info:
                    final_name = provider_name or ("Free Shipping" if cost == 0.0 else "Standard Delivery")
                    final_description = text[:200] if len(text) > 200 else text

                    # Deduplicate based on name, cost, delivery time, and type
                    provider_key = f"{final_name}_{cost}_{delivery_time}_{delivery_type}"
                    if provider_key in seen_providers:
                        logger.debug(f"[SHIPPING] Skipping duplicate: {provider_key}")
                        continue
                    seen_providers.add(provider_key)

                    providers.append(
                        ShippingProvider(
                            name=final_name,
                            price=cost,
                            currency=currency if cost is not None else None,
                            delivery_time=delivery_time or "Unknown",
                            delivery_type=delivery_type,
                            description=final_description,
                        )
                    )
                    logger.info(
                        f"[SHIPPING] Added: {final_name}, {cost if cost is not None else 'Price TBD'} {currency if cost is not None else ''}, {delivery_time or 'Unknown'}, Type: {delivery_type}"
                    )
                else:
                    logger.debug(f"[SHIPPING] Skipping section - no confident shipping info found")

            if providers:
                logger.info(f"[SHIPPING] Extracted {len(providers)} shipping provider(s) from product page")
            else:
                logger.warning("[SHIPPING] No shipping providers found on product page")
                logger.info(f"[SHIPPING] Diagnostic info:")
                logger.info(f"  - Total sections analyzed: {len(unique_sections)}")
                logger.info(f"  - Shipping-related sections: {len([s for s in unique_sections if self._is_shipping_related(s.get_text(strip=True).lower())])}")
                logger.info(f"  - Consider checking if shipping info requires cart/checkout navigation for this site")

        except Exception as e:
            logger.warning(f"[SHIPPING] Error extracting shipping providers: {e}")
            logger.debug(f"[SHIPPING] Traceback: {traceback.format_exc()}")

        return providers

    async def scrape_multiple(self, analyses: List[AnalysisResult]) -> List[ScrapedProduct]:
        """
        Scrape multiple products concurrently with error handling.

        Args:
            analyses: List of AnalysisResult schemas

        Returns:
            List of ScrapedProduct schemas
        """
        logger.info(f" Starting concurrent scrape of {len(analyses)} products")

        # Scrape all products concurrently
        tasks = [self.scrape(analysis) for analysis in analyses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None and exceptions, log errors
        products = []
        for i, result in enumerate(results):
            if isinstance(result, ScrapedProduct):
                products.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Product {i+1} failed with exception: {result}")
            else:
                logger.warning(f"Product {i+1} returned None")

        logger.info(f" Successfully scraped {len(products)}/{len(analyses)} products")

        return products
