"""
Website Analyzer Service
Analyzes websites for scraping readiness using Playwright async API
Returns AnalysisResult Pydantic schema (Kafka-ready)
"""
import logging
import random
import traceback
from typing import Optional, Dict
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

from src.schemas.messages import AnalysisResult
from src.config import settings

logger = logging.getLogger(__name__)


class AnalyzerService:
    """Service for website analysis using Playwright with error handling"""

    def __init__(self, timeout: int = None, headless: bool = True):
        self.playwright = None
        self.browser = None
        self.timeout = timeout or settings.page_timeout
        self.headless = headless

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Start Playwright and browser with error handling."""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            logger.info(" Analyzer started")
        except Exception as e:
            logger.error(f"Failed to start analyzer: {e}")
            logger.debug(f"Stack trace: {traceback.format_exc()}")
            raise

    async def close(self):
        """Close browser and Playwright with proper cleanup."""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            logger.info(" Analyzer closed")
        except Exception as e:
            logger.error(f"Error closing analyzer: {e}")
            # Don't raise here - best effort cleanup

    async def analyze_website(
        self,
        url: str,
        product_path: Optional[str] = None,
        checkout_path: Optional[str] = None,
        auto_discover: bool = True,
    ) -> AnalysisResult:
        """
        Analyze website for scraping readiness.

        Args:
            url: Website URL to analyze
            product_path: Optional product page path
            checkout_path: Optional checkout page path
            auto_discover: Auto-discover product URLs

        Returns:
            AnalysisResult Pydantic schema
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path
        base_url = f"{parsed_url.scheme}://{domain}" if parsed_url.scheme else f"https://{domain}"

        logger.info(f" Analyzing {domain}...")

        # Ensure browser is started
        if not self.browser:
            await self.start()

        # Check robots.txt
        robots_result = await self._check_robots_txt(base_url, url)

        # If robots.txt blocks critical paths, stop here with clear message
        if not robots_result["base_allowed"]:
            logger.error(f"*** ANALYSIS STOPPED: {robots_result['message']} ***")
            logger.error(f"The website's robots.txt explicitly blocks scraping of critical paths.")
            logger.error(f"Blocked paths: {', '.join(robots_result['blocked_paths'])}")
            logger.error(f"You cannot scrape this site without violating robots.txt rules.")
            logger.error(f"Recommendation: Contact the site owner for API access or permission.")

            # Return analysis with can_scrape=False
            return AnalysisResult(
                domain=domain,
                product_url=None,
                source_website=domain,
                can_scrape=False,
                selectors={},
                use_stealth=False,
                scrape_delay=robots_result.get("crawl_delay", 3),
                robots_txt_allowed=False,
                robots_txt_message=robots_result["message"],
                bot_protection_detected=False,
                bot_protection_type=[],
                discovery_method="robots_txt_blocked",
                confidence_score=0.0,
                notes=f"SCRAPING BLOCKED: {robots_result['message']}. Blocked paths: {', '.join(robots_result['blocked_paths'])}",
            )

        # Check bot protection (combine robots.txt detection with other checks)
        bot_protection = await self._check_bot_protection(url)

        # If robots.txt returned 403, it indicates bot protection
        if robots_result.get("bot_protection_detected"):
            bot_protection["detected"] = True
            if "robots.txt 403" not in bot_protection.get("types", []):
                bot_protection.setdefault("types", []).append("robots.txt 403")

        # Discover product URL if needed
        product_url = None
        if product_path:
            # Use explicit product path
            product_url = urljoin(base_url, product_path)
        elif url and ("/product/" in url or "/catalogue/" in url or "/item/" in url or "/p/" in url):
            # URL looks like a product page, use it directly
            product_url = url
        elif auto_discover:
            # Try to discover product URL from the page
            product_url = await self.discover_product_url(url)
        else:
            # Just use the URL as-is
            product_url = url

        # Detect selectors if product URL found
        selectors = {}
        if product_url:
            selectors = await self.detect_universal_selectors(product_url)

        # Determine if we can scrape
        can_scrape = robots_result["base_allowed"] and not bot_protection["detected"] and product_url is not None

        # Create AnalysisResult schema
        analysis = AnalysisResult(
            domain=domain,
            product_url=product_url,
            source_website=domain,
            can_scrape=can_scrape,
            selectors=selectors,
            use_stealth=bot_protection["detected"],
            scrape_delay=max(3, robots_result.get("crawl_delay", 0) or 0),
            robots_txt_allowed=robots_result["base_allowed"],
            robots_txt_message=robots_result["message"],
            crawl_delay=robots_result.get("crawl_delay"),
            bot_protection_detected=bot_protection["detected"],
            protection_types=bot_protection.get("types", []),
            protection_confidence=bot_protection.get("confidence", "low"),
        )

        logger.info(f" Analysis complete - Can scrape: {can_scrape}")

        # Future: Publish to Kafka topic 'analysis-results'
        # await kafka_producer.send('analysis-results', analysis.model_dump_json())

        return analysis

    def _score_product_url(self, url: str) -> int:
        """Score a URL based on likelihood it's a product page. Higher = more likely."""
        score = 0
        url_lower = url.lower()

        # High confidence patterns (10-20 points)
        high_confidence = [
            "/product/",
            "/products/",
            "/p/",
            "/item/",
            "/vare/",
            "/catalogue/",
            "/catalog/",
            "/pd/",
            "/dp/",
        ]
        for pattern in high_confidence:
            if pattern in url_lower:
                score += 20
                break

        # Product ID patterns (15 points)
        import re

        if re.search(r"/\d{5,}", url) or re.search(r"[-_]\d{5,}", url):
            score += 15

        # Negative patterns - these are NOT products
        negative_patterns = settings.non_product_patterns + [
            "/cart/",
            "/checkout/",
            "/account/",
            "/login/",
            "/register/",
        ]
        for pattern in negative_patterns:
            if pattern in url_lower:
                score -= 50
                break

        # Medium confidence - looks like product path (5 points)
        if url.count("/") >= 3 and not url.endswith("/"):
            score += 5

        return score

    def _quick_filter_non_products(self, urls: list) -> list:
        """Quickly filter out obvious non-product URLs before validation."""
        filtered = []
        for url in urls:
            score = self._score_product_url(url)
            if score > -10:  # Keep URLs that aren't obviously bad
                filtered.append((url, score))

        # Sort by score (highest first)
        filtered.sort(key=lambda x: x[1], reverse=True)
        return [url for url, score in filtered]

    async def _discover_category_urls(self, page, base_url: str) -> list:
        """
        Discover category/collection URLs from homepage.

        Args:
            page: Playwright page object
            base_url: Base URL of the site

        Returns:
            List of category URLs
        """
        category_selectors = [
            # Navigation patterns
            "nav a[href*='/category/']",
            "nav a[href*='/categories/']",
            "nav a[href*='/collection/']",
            "nav a[href*='/shop/']",
            "nav a[href*='/produkter/']",
            "nav a[href*='/category']",
            # Menu patterns
            "[class*='menu'] a[href^='/']",
            "[class*='nav'] a[href^='/']",
            "[class*='category'] a[href]",
            "[class*='collection'] a[href]",
            # Specific for Danish sites
            "a[href*='/hudpleje/']",
            "a[href*='/makeup/']",
            "a[href*='/parfume/']",
            "a[href*='/haar/']",
        ]

        categories = []
        for selector in category_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for elem in elements[:5]:  # Limit per selector
                    href = await elem.get_attribute("href")
                    if href and not href.startswith(("#", "javascript:", "mailto:")):
                        full_url = urljoin(base_url, href)
                        if full_url not in categories and full_url != base_url:
                            # Avoid overly generic URLs
                            if not any(
                                x in full_url.lower()
                                for x in ["/about", "/contact", "/login", "/register", "/cart", "/checkout"]
                            ):
                                categories.append(full_url)
            except Exception as e:
                logger.debug(f"Category selector '{selector}' failed: {e}")

        # Deduplicate and limit
        unique_categories = list(dict.fromkeys(categories))[:10]  # Top 10 categories
        logger.info(f"[CATEGORY] Found {len(unique_categories)} potential category URLs")
        return unique_categories

    async def discover_product_url(self, url: str, max_retries: int = 2) -> Optional[str]:
        """
        Discover a product URL from the homepage with improved speed and reliability.
        Uses intelligent filtering, scoring, and validation.

        Args:
            url: Homepage URL
            max_retries: Maximum retry attempts

        Returns:
            Product URL or None
        """
        for attempt in range(max_retries):
            page = None
            try:
                page = await self.browser.new_page()
                page.set_default_timeout(self.timeout)

                logger.info(f"Discovering products (attempt {attempt + 1}/{max_retries})...")
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                # STEP 1: Quick check for schema.org Product markup
                try:
                    schema_products = await page.query_selector_all('[itemtype*="schema.org/Product"]')
                    if schema_products:
                        logger.info(f"[SCHEMA] Found {len(schema_products)} schema.org Product elements")
                        for elem in schema_products[:3]:  # Check first 3
                            link = await elem.query_selector("a[href]")
                            if link:
                                href = await link.get_attribute("href")
                                if href:
                                    full_url = urljoin(url, href)
                                    logger.info(f"[SCHEMA] Found product via schema.org: {full_url}")
                                    await page.close()
                                    return full_url
                except Exception as e:
                    logger.debug(f"Schema.org check failed: {e}")

                # STEP 2: Collect all product links with progressive selectors
                selector_groups = [
                    # Group 1: High-confidence product patterns
                    [
                        "a[href*='/product/']",
                        "a[href*='/products/']",
                        "a[href*='/p/']",
                        "a[href*='/item/']",
                        "a[href*='/vare/']",
                        "a[href*='/catalogue/']",
                        "a[href*='/pd/']",
                    ],
                    # Group 2: Product container patterns
                    [
                        ".product-item a[href]",
                        ".product-card a[href]",
                        "[class*='product'] a[href]",
                        "article a[href]",
                        ".item a[href]",
                        "[data-product-id] a[href]",
                    ],
                    # Group 3: Semantic areas
                    [
                        "main a[href^='/']",
                        "[role='main'] a[href^='/']",
                        ".content a[href^='/']",
                    ],
                ]

                all_candidates = []

                for group_idx, selectors in enumerate(selector_groups):
                    logger.info(f"[DISCOVER] Scanning selector group {group_idx + 1}/{len(selector_groups)}")

                    for selector in selectors:
                        try:
                            elements = await page.query_selector_all(selector)
                            if elements:
                                logger.debug(f"[DISCOVER] Found {len(elements)} links with '{selector}'")
                                for elem in elements:
                                    href = await elem.get_attribute("href")
                                    if href and not href.startswith(("#", "javascript:", "mailto:")):
                                        full_url = urljoin(url, href)
                                        if full_url not in all_candidates and full_url != url:
                                            all_candidates.append(full_url)
                        except Exception as e:
                            logger.debug(f"Selector '{selector}' failed: {e}")

                    # If we found good candidates in this group, don't need to go broader
                    if len(all_candidates) >= 10 and group_idx == 0:
                        logger.info(
                            f"[DISCOVER] Found {len(all_candidates)} high-confidence candidates, skipping broader search"
                        )
                        break
                    elif len(all_candidates) >= 20:
                        logger.info(f"[DISCOVER] Found {len(all_candidates)} candidates, proceeding to validation")
                        break

                if not all_candidates:
                    logger.warning(f"No product link candidates found on attempt {attempt + 1}")
                    await page.close()
                    if attempt < max_retries - 1:
                        continue
                    return None

                logger.info(f"[DISCOVER] Found {len(all_candidates)} total link candidates")

                # STEP 3: Filter obvious non-products and score
                filtered_candidates = self._quick_filter_non_products(all_candidates)
                logger.info(
                    f"[FILTER] {len(filtered_candidates)} candidates after filtering (removed {len(all_candidates) - len(filtered_candidates)})"
                )

                if not filtered_candidates:
                    logger.warning("All candidates filtered out as non-products")
                    await page.close()
                    if attempt < max_retries - 1:
                        continue
                    return None

                await page.close()

                # STEP 4: Validate top candidates (randomly selected from top-scored for variety)
                top_candidates = filtered_candidates[: min(10, len(filtered_candidates))]  # Top 10 by score
                max_to_validate = min(settings.max_validation_attempts, len(top_candidates))
                candidates_to_check = (
                    random.sample(top_candidates, max_to_validate)
                    if len(top_candidates) >= max_to_validate
                    else top_candidates
                )
                logger.info(
                    f"[VALIDATION] Randomly validating {max_to_validate} from top {len(top_candidates)} candidates..."
                )

                for idx, candidate_url in enumerate(candidates_to_check):
                    logger.info(f"[VALIDATION] Checking candidate {idx + 1}/{max_to_validate}: {candidate_url}")
                    if await self._is_valid_product_page(candidate_url):
                        logger.info(f" Discovered valid product URL: {candidate_url}")
                        return candidate_url

                logger.warning(f"No valid product pages found after validating {max_to_validate} candidates")

                # STEP 5: If no products found, try navigating to categories
                logger.info("[CATEGORY] No products on homepage, attempting category navigation...")

                # Re-open page for category discovery
                category_page = await self.browser.new_page()
                category_page.set_default_timeout(self.timeout)
                await category_page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                category_urls = await self._discover_category_urls(category_page, url)
                await category_page.close()

                if category_urls:
                    logger.info(f"[CATEGORY] Found {len(category_urls)} categories, randomly checking 3...")

                    # Randomly select 3 categories to check
                    num_categories_to_check = min(3, len(category_urls))
                    selected_categories = random.sample(category_urls, num_categories_to_check)

                    # Try each selected category
                    for cat_idx, category_url in enumerate(selected_categories):
                        logger.info(
                            f"[CATEGORY] Checking category {cat_idx + 1}/{num_categories_to_check}: {category_url}"
                        )

                        try:
                            cat_page = await self.browser.new_page()
                            cat_page.set_default_timeout(self.timeout)
                            await cat_page.goto(category_url, wait_until="domcontentloaded", timeout=self.timeout)

                            # Look for products on category page
                            cat_candidates = []
                            product_selectors = [
                                ".product-item a[href]",
                                ".product-card a[href]",
                                "[class*='product'] a[href]",
                                "article a[href]",
                            ]

                            for selector in product_selectors:
                                try:
                                    elements = await cat_page.query_selector_all(selector)
                                    if elements:
                                        logger.debug(f"[CATEGORY] Found {len(elements)} links with '{selector}'")
                                        for elem in elements[:20]:  # Limit to 20 per selector
                                            href = await elem.get_attribute("href")
                                            if href and not href.startswith(("#", "javascript:", "mailto:")):
                                                full_url = urljoin(category_url, href)
                                                if full_url not in cat_candidates and full_url != category_url:
                                                    cat_candidates.append(full_url)
                                except Exception as e:
                                    logger.debug(f"Category selector '{selector}' failed: {e}")

                            await cat_page.close()

                            if cat_candidates:
                                # Filter and validate category candidates
                                filtered_cat = self._quick_filter_non_products(cat_candidates)
                                logger.info(f"[CATEGORY] Found {len(filtered_cat)} product candidates in category")

                                # Randomly validate 3 from top candidates in this category
                                top_cat_candidates = filtered_cat[: min(10, len(filtered_cat))]  # Top 10 by score
                                num_to_validate = min(3, len(top_cat_candidates))
                                cat_products_to_check = (
                                    random.sample(top_cat_candidates, num_to_validate)
                                    if len(top_cat_candidates) >= num_to_validate
                                    else top_cat_candidates
                                )

                                for prod_idx, candidate_url in enumerate(cat_products_to_check):
                                    logger.info(
                                        f"[CATEGORY] Validating product {prod_idx + 1}/{num_to_validate}: {candidate_url}"
                                    )
                                    if await self._is_valid_product_page(candidate_url):
                                        logger.info(f" Discovered product via category navigation: {candidate_url}")
                                        return candidate_url

                        except Exception as e:
                            logger.debug(f"Error checking category {category_url}: {e}")
                            continue

                    logger.warning("No valid products found in any category pages")
                else:
                    logger.warning("No category URLs found on homepage")

                if attempt < max_retries - 1:
                    logger.info("Retrying product discovery...")
                    continue

                return None

            except PlaywrightTimeoutError:
                logger.warning(f"Timeout discovering products on attempt {attempt + 1}")
                if page:
                    try:
                        await page.close()
                    except:
                        pass
                if attempt < max_retries - 1:
                    continue
                return None
            except Exception as e:
                logger.error(f"Error discovering product URL (attempt {attempt + 1}): {e}")
                logger.debug(f"Stack trace: {traceback.format_exc()}")
                if page:
                    try:
                        await page.close()
                    except:
                        pass
                if attempt < max_retries - 1:
                    continue
                return None

        return None

    async def detect_universal_selectors(self, url: str) -> Dict[str, Optional[str]]:
        """
        Detect universal selectors for product page with error handling.

        Args:
            url: Product page URL

        Returns:
            Dictionary of detected selectors
        """
        selectors = {
            "title": None,
            "price": None,
            "add_to_cart": None,
            "cart_button": None,
            "checkout_button": None,
            "shipping": None,
        }

        page = None
        try:
            page = await self.browser.new_page()
            page.set_default_timeout(self.timeout)
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

            # Detect title with error handling for each pattern
            for pattern in ["//h1", "//h2", "//*[@class='title']"]:
                try:
                    element = await page.query_selector(f"xpath={pattern}")
                    if element:
                        selectors["title"] = pattern
                        logger.info(f"[DETECT] Title selector: {pattern}")
                        break
                except Exception as e:
                    logger.debug(f"Title pattern '{pattern}' failed: {e}")

            # Detect price with error handling
            for pattern in [
                "//*[contains(@class, 'price') and not(contains(@class, 'old'))]",
                "//*[@itemprop='price']",
                "//*[contains(@class, 'product-price')]",
            ]:
                try:
                    element = await page.query_selector(f"xpath={pattern}")
                    if element:
                        selectors["price"] = pattern
                        logger.info(f"[DETECT] Price selector: {pattern}")
                        break
                except Exception as e:
                    logger.debug(f"Price pattern '{pattern}' failed: {e}")

            await page.close()

            detected_count = sum(1 for v in selectors.values() if v)
            logger.info(f"Detected {detected_count}/6 selectors")

        except PlaywrightTimeoutError:
            logger.warning("Timeout detecting selectors")
            if page:
                try:
                    await page.close()
                except:
                    pass
        except Exception as e:
            logger.error(f"Error detecting selectors: {e}")
            logger.debug(f"Stack trace: {traceback.format_exc()}")
            if page:
                try:
                    await page.close()
                except:
                    pass

        return selectors

    async def _is_valid_product_page(self, url: str) -> bool:
        """
        Validate if a URL is an actual product page (not article/category/blog).
        Enhanced with faster checks and better indicators.

        Args:
            url: URL to validate

        Returns:
            True if it's a valid product page, False otherwise
        """
        page = None
        try:
            page = await self.browser.new_page()
            # Shorter timeout for validation - fail fast on slow pages
            page.set_default_timeout(8000)

            await page.goto(url, wait_until="domcontentloaded", timeout=8000)

            # Check 1: URL patterns that indicate non-product pages
            url_lower = url.lower()
            non_product_patterns = settings.non_product_patterns

            for pattern in non_product_patterns:
                if pattern in url_lower:
                    logger.debug(f"[VALIDATION] URL contains non-product pattern '{pattern}'")
                    await page.close()
                    return False

            # Check 2: Schema.org Product markup (strongest indicator)
            try:
                schema_product = await page.query_selector('[itemtype*="schema.org/Product"]')
                if schema_product:
                    logger.info(f"[VALIDATION] ✓ Found schema.org Product markup: {url}")
                    await page.close()
                    return True
            except:
                pass

            # Check 3: JSON-LD structured data
            try:
                json_ld_script = await page.query_selector('script[type="application/ld+json"]')
                if json_ld_script:
                    content = await json_ld_script.inner_text()
                    if '"@type":"Product"' in content or '"@type": "Product"' in content:
                        logger.info(f"[VALIDATION] [OK] Found JSON-LD Product data: {url}")
                        await page.close()
                        return True
            except:
                pass

            # Check 4: Look for add-to-cart button (strong indicator)
            add_to_cart_selectors = settings.add_to_cart_selectors[:10]  # Use first 10 from config

            for selector in add_to_cart_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        is_visible = await button.is_visible()
                        if is_visible:
                            logger.info(f"[VALIDATION] [OK] Found visible add-to-cart button: {url}")
                            await page.close()
                            return True
                except:
                    continue

            # Check 5: Look for price element with text validation
            price_selectors = [
                "[class*='price']:not([class*='old']):not([class*='original'])",
                "[data-testid*='price']",
                "[itemprop='price']",
                ".woocommerce-Price-amount",
                "span[class*='Price']",
                "div[class*='price']",
            ]

            has_price = False
            for selector in price_selectors:
                try:
                    price_elem = await page.query_selector(selector)
                    if price_elem:
                        text = await price_elem.inner_text()
                        # Check if it contains currency symbols or "kr"
                        if any(char in text for char in ["$", "€", "£", "kr", "DKK", "SEK", "NOK"]):
                            has_price = True
                            logger.debug(f"[VALIDATION] Found price: {text.strip()[:50]}")
                            break
                except:
                    continue

            # Check 6: Look for product-specific elements
            product_indicators = [
                "[class*='product-detail']",
                "[class*='product-page']",
                "[class*='product-info']",
                "[id*='product']",
                "[data-product-id]",
                ".product-form",
                "form[action*='cart']",
                "form[action*='add']",
            ]

            has_product_indicator = False
            for selector in product_indicators:
                try:
                    elem = await page.query_selector(selector)
                    if elem:
                        has_product_indicator = True
                        logger.debug(f"[VALIDATION] Found product indicator: {selector}")
                        break
                except:
                    continue

            # Check 7: Look for product images (gallery pattern)
            try:
                images = await page.query_selector_all(
                    'img[src*="product"], img[alt*="product"], .product-image img, [class*="gallery"] img'
                )
                has_product_images = len(images) >= 2  # Product pages typically have multiple images
                if has_product_images:
                    logger.debug(f"[VALIDATION] Found {len(images)} product-related images")
            except:
                has_product_images = False

            await page.close()

            # Scoring system: need at least 2 positive indicators
            score = 0
            if has_price:
                score += 2
            if has_product_indicator:
                score += 1
            if has_product_images:
                score += 1

            is_valid = score >= 2

            if is_valid:
                logger.info(f"[VALIDATION] [OK] Confirmed product page (score: {score}/4): {url}")
            else:
                logger.debug(f"[VALIDATION] [SKIP] Not a product page (score: {score}/4): {url}")

            return is_valid

        except PlaywrightTimeoutError:
            logger.debug(f"[VALIDATION] Timeout validating (skipping): {url}")
            if page:
                try:
                    await page.close()
                except:
                    pass
            return False
        except Exception as e:
            logger.debug(f"[VALIDATION] Error validating (assuming invalid): {str(e)[:100]}")
            if page:
                try:
                    await page.close()
                except:
                    pass
            return False

    async def _check_robots_txt(self, base_url: str, url: str) -> Dict:
        """Check robots.txt for scraping permissions with detailed path analysis"""
        import urllib.robotparser
        from urllib.parse import urljoin
        import aiohttp
        from pathlib import Path
        from datetime import datetime

        robots_url = urljoin(base_url, "/robots.txt")
        logger.info(f"[ROBOTS.TXT] Checking {robots_url}")

        # Critical paths that need to be allowed for successful scraping
        critical_paths = {
            "products": ["/product", "/products", "/catalogue", "/catalog", "/item", "/vare"],
            "cart": ["/cart", "/basket", "/kurv", "/shopping-cart", "/warenkorb"],
            "checkout": ["/checkout", "/kasse", "/order", "/bestilling"],
        }

        result = {
            "base_allowed": True,
            "message": "Allowed",
            "crawl_delay": 3,
            "blocked_paths": [],
            "allowed_paths": [],
            "warnings": [],
            "robots_txt_content": None,
            "bot_protection_detected": False,
        }

        # Create robots.txt log file
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d")
        robots_log_file = log_dir / f"robots_txt_{timestamp}.log"

        def log_to_file(message: str):
            """Write to dedicated robots.txt log file"""
            with open(robots_log_file, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")

        try:
            log_to_file(f"{'='*80}")
            log_to_file(f"CHECKING: {robots_url}")
            log_to_file(f"BASE URL: {base_url}")

            # Fetch robots.txt with proper User-Agent to avoid bot protection
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(robots_url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        robots_content = await response.text()
                        result["robots_txt_content"] = robots_content
                        logger.info(f"[ROBOTS.TXT] Successfully fetched ({len(robots_content)} bytes)")
                        log_to_file(f"STATUS: Successfully fetched ({len(robots_content)} bytes)")
                        log_to_file(f"\nCONTENT:\n{robots_content}\n")

                        # Parse robots.txt
                        rp = urllib.robotparser.RobotFileParser()
                        rp.parse(robots_content.splitlines())

                        log_to_file(f"\nPATH ANALYSIS:")
                        log_to_file(f"{'-'*80}")

                        # Check critical paths
                        for category, paths in critical_paths.items():
                            category_blocked = []
                            category_allowed = []

                            log_to_file(f"\nChecking {category.upper()} paths:")

                            for path in paths:
                                test_url = urljoin(base_url, path)
                                if rp.can_fetch("*", test_url):
                                    category_allowed.append(path)
                                    log_to_file(f"  ✓ ALLOWED: {path}")
                                else:
                                    category_blocked.append(path)
                                    log_to_file(f"  ✗ BLOCKED: {path}")

                            if category_blocked:
                                result["blocked_paths"].extend(category_blocked)
                                warning_msg = f"{category.upper()} paths blocked: {', '.join(category_blocked)}"
                                result["warnings"].append(warning_msg)
                                logger.warning(f"[ROBOTS.TXT] WARNING: {warning_msg}")
                                log_to_file(f"\n⚠️  WARNING: {warning_msg}")

                            if category_allowed:
                                result["allowed_paths"].extend(category_allowed)
                                logger.info(
                                    f"[ROBOTS.TXT] ALLOWED: {category.upper()} paths - {', '.join(category_allowed)}"
                                )

                        # Determine overall status
                        log_to_file(f"\n{'-'*80}")
                        log_to_file(f"SUMMARY:")

                        if result["blocked_paths"]:
                            result["base_allowed"] = False
                            result[
                                "message"
                            ] = f"Critical paths blocked by robots.txt: {', '.join(result['blocked_paths'])}"

                            # Create user-friendly message
                            blocked_categories = []
                            if any(p in result["blocked_paths"] for p in critical_paths["products"]):
                                blocked_categories.append("PRODUCTS")
                            if any(p in result["blocked_paths"] for p in critical_paths["cart"]):
                                blocked_categories.append("CART")
                            if any(p in result["blocked_paths"] for p in critical_paths["checkout"]):
                                blocked_categories.append("CHECKOUT")

                            user_message = f"SCRAPING NOT ALLOWED - robots.txt blocks: {', '.join(blocked_categories)}"
                            logger.error(f"[ROBOTS.TXT] *** {user_message} ***")
                            logger.error(f"[ROBOTS.TXT] Blocked paths: {', '.join(result['blocked_paths'])}")
                            logger.error(
                                f"[ROBOTS.TXT] This site does not allow automated scraping of these critical paths."
                            )
                            logger.error(
                                f"[ROBOTS.TXT] Recommendation: Contact site owner for API access or scraping permission."
                            )

                            log_to_file(f"RESULT: ⛔ SCRAPING NOT ALLOWED")
                            log_to_file(f"BLOCKED CATEGORIES: {', '.join(blocked_categories)}")
                            log_to_file(f"BLOCKED PATHS: {', '.join(result['blocked_paths'])}")
                            log_to_file(
                                f"ALLOWED PATHS: {', '.join(result['allowed_paths']) if result['allowed_paths'] else 'None'}"
                            )
                            log_to_file(f"RECOMMENDATION: Contact site owner for API access or permission")

                            result["message"] = user_message
                        else:
                            logger.info(f"[ROBOTS.TXT] SUCCESS: All critical paths are allowed for scraping")
                            log_to_file(f"RESULT: ✅ SCRAPING ALLOWED")
                            log_to_file(f"All critical paths ({len(result['allowed_paths'])}) are accessible")
                            result["message"] = "All critical paths allowed"

                        # Check for crawl delay
                        crawl_delay = rp.crawl_delay("*")
                        if crawl_delay:
                            result["crawl_delay"] = int(crawl_delay)
                            logger.info(f"[ROBOTS.TXT] Crawl delay: {crawl_delay} seconds")
                            log_to_file(f"CRAWL DELAY: {crawl_delay} seconds")
                        else:
                            log_to_file(f"CRAWL DELAY: None specified (using default)")

                    elif response.status == 404:
                        logger.info(f"[ROBOTS.TXT] No robots.txt found (404) - assuming allowed")
                        log_to_file(f"STATUS: 404 Not Found - No robots.txt file")
                        log_to_file(f"RESULT: ✅ SCRAPING ALLOWED (no restrictions)")
                        result["message"] = "No robots.txt (assumed allowed)"
                    elif response.status == 403:
                        logger.warning(f"[ROBOTS.TXT] 403 Forbidden - Bot protection detected")
                        log_to_file(f"STATUS: 403 Forbidden - Bot protection blocking robots.txt access")
                        log_to_file(f"RESULT: ⚠️ BOT PROTECTION DETECTED (assuming allowed but using stealth mode)")
                        result["message"] = "Bot protection detected (403 on robots.txt)"
                        result["bot_protection_detected"] = True
                    else:
                        logger.warning(f"[ROBOTS.TXT] Unexpected status {response.status} - assuming allowed")
                        log_to_file(f"STATUS: {response.status} - Unexpected response")
                        log_to_file(f"RESULT: ✅ SCRAPING ALLOWED (assuming no restrictions)")
                        result["message"] = f"robots.txt status {response.status} (assumed allowed)"

        except Exception as e:
            logger.warning(f"[ROBOTS.TXT] Error checking robots.txt: {e} - assuming allowed")
            log_to_file(f"ERROR: {e}")
            log_to_file(f"RESULT: ✅ SCRAPING ALLOWED (error occurred, assuming no restrictions)")
            result["message"] = f"Error checking robots.txt: {e} (assumed allowed)"

        log_to_file(f"{'='*80}\n")
        return result

    async def _check_bot_protection(self, url: str) -> Dict:
        """Check for bot protection"""
        # Simplified - assume no protection
        return {"detected": False, "types": [], "confidence": "low"}
