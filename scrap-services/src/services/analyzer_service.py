"""
Website Analyzer Service - Recreated from Scratch
Intelligently analyzes websites and discovers product pages for scraping.
Returns AnalysisResult Pydantic schema.

Key Features:
- Detects if provided URL is already a product page
- Intelligently discovers random product pages if not
- Works universally across all website structures
- Maintains robots.txt and bot protection checks
- Ensures variety by selecting different products each time
"""
import logging
import random
import traceback
import re
import urllib.robotparser
import aiohttp
from typing import Optional, Dict, List, Tuple, Set
from urllib.parse import urlparse, urljoin
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

from src.schemas.messages import AnalysisResult
from src.config import settings

logger = logging.getLogger(__name__)


class AnalyzerService:
    """
    Service for intelligent website analysis and product discovery.

    This service determines whether a URL is a product page, and if not,
    intelligently discovers random product pages across any website structure.
    """

    # Class-level cache to track selected URLs per domain for variety
    _selected_products_cache: Dict[str, Set[str]] = {}
    _max_cache_size_per_domain: int = 100

    def __init__(self, timeout: int = None, headless: bool = True):
        """Initialize the analyzer service."""
        self.playwright = None
        self.browser = None
        self.timeout = timeout or settings.page_timeout
        self.headless = settings.headless_mode if headless is None else headless

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def start(self):
        """Start Playwright and browser."""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            logger.info("[OK] Analyzer started")
        except Exception as e:
            logger.error(f"Failed to start analyzer: {e}")
            logger.debug(f"Stack trace: {traceback.format_exc()}")
            raise

    async def close(self):
        """Close browser and Playwright."""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            logger.info("[OK] Analyzer closed")
        except Exception as e:
            logger.error(f"Error closing analyzer: {e}")

    async def analyze_website(
        self,
        url: str,
        product_path: Optional[str] = None,
        checkout_path: Optional[str] = None,
        auto_discover: bool = True,
    ) -> AnalysisResult:
        """
        Analyze website and find/validate product pages.

        Args:
            url: Website URL to analyze
            product_path: Optional explicit product page path
            checkout_path: Optional checkout page path (unused, kept for compatibility)
            auto_discover: Enable automatic product discovery

        Returns:
            AnalysisResult with product URL and scraping readiness info
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path
        base_url = f"{parsed_url.scheme}://{domain}" if parsed_url.scheme else f"https://{domain}"

        logger.info(f"[ANALYZE] Analyzing {domain}...")

        # Ensure browser is started
        if not self.browser:
            await self.start()

        # STEP 1: Check robots.txt
        robots_result = await self._check_robots_txt(base_url, url)

        # If robots.txt blocks critical paths, stop immediately
        if not robots_result["base_allowed"]:
            logger.error(f"*** ANALYSIS STOPPED: {robots_result['message']} ***")
            logger.error("The website's robots.txt explicitly blocks scraping of critical paths.")
            logger.error(f"Blocked paths: {', '.join(robots_result['blocked_paths'])}")

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
                protection_types=[],
                protection_confidence="low",
                notes=f"SCRAPING BLOCKED: {robots_result['message']}",
            )

        # STEP 2: Check bot protection
        bot_protection = await self._check_bot_protection(url)
        if robots_result.get("bot_protection_detected"):
            bot_protection["detected"] = True
            bot_protection.setdefault("types", []).append("robots.txt 403")

        # STEP 3: Determine product URL
        product_url = None

        if product_path:
            # Explicit product path provided
            product_url = urljoin(base_url, product_path)
            logger.info(f"[PRODUCT] Using explicit product path: {product_url}")

        elif auto_discover:
            # Intelligently determine if URL is already a product page or discover one
            product_url = await self._find_product_page(url, domain, base_url)
        else:
            # Use URL as-is
            product_url = url
            logger.info(f"[PRODUCT] Using provided URL as-is: {product_url}")

        # STEP 4: Detect selectors if product URL found
        selectors = {}
        if product_url:
            selectors = await self._detect_selectors(product_url)

        # STEP 5: Determine if we can scrape
        can_scrape = (
            robots_result["base_allowed"]
            and not bot_protection["detected"]
            and product_url is not None
        )

        # Create analysis result
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

        logger.info(f"[OK] Analysis complete - Can scrape: {can_scrape}")
        return analysis

    async def _find_product_page(self, url: str, domain: str, base_url: str) -> Optional[str]:
        """
        Intelligently find a product page URL.

        Strategy:
        1. Check if the provided URL is already a product page
        2. If not, discover and randomly select a product page from the site
        3. Ensure variety by avoiding previously selected products

        Args:
            url: The URL to analyze
            domain: The website domain
            base_url: The base URL of the site

        Returns:
            Product page URL or None if not found
        """
        # Check if URL is already a product page
        logger.info("[PRODUCT] Checking if URL is already a product page...")
        is_product = await self._is_product_page(url)

        if is_product:
            logger.info(f"[OK] Provided URL is already a product page: {url}")
            return url

        # URL is not a product page, navigate through categories to find products
        logger.info("[PRODUCT] URL is not a product page, navigating through categories...")
        discovered_product = await self._navigate_to_product(url, domain, base_url)

        if discovered_product:
            logger.info(f"[OK] Discovered random product page: {discovered_product}")
            return discovered_product

        logger.warning("[WARN] Could not discover any product pages")
        return None

    async def _is_product_page(self, url: str) -> bool:
        """
        Determine if a URL is a product page by validating essential product elements.

        A valid product page should have at least 3 out of 4 core elements:
        1. Product title (h1)
        2. Product description or details
        3. Price
        4. Add-to-cart/basket button

        Also checks for product-specific URL patterns.

        Args:
            url: URL to check

        Returns:
            True if it's likely a product page, False otherwise
        """
        page = None
        try:
            # Quick URL pattern check first (fast)
            url_lower = url.lower()

            # Exclude homepages (even if they have product schema for featured items)
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            # Homepage if path is empty or just domain
            if not path or path == '' or len(path.split('/')) == 0:
                logger.debug(f"[PRODUCT] URL is homepage, not a product page")
                return False

            # Exclude non-product patterns
            for pattern in settings.non_product_patterns:
                if pattern in url_lower:
                    logger.debug(f"[PRODUCT] URL contains non-product pattern: {pattern}")
                    return False

            # Positive URL patterns that suggest product page (e.g., underscore+numbers: _769926)
            import re
            has_product_url_pattern = bool(re.search(r'_\d{5,}|/p/\d+|/product/|/produkt/', url_lower))

            # Open page to check content
            page = await self.browser.new_page()
            page.set_default_timeout(10000)  # 10 second timeout for faster checks
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)

            # Wait for dynamic content
            try:
                await page.wait_for_timeout(1500)
            except:
                pass

            # Element 1: Product Title (h1)
            title_found = False
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
                        if text and len(text.strip()) > 5:  # Must have meaningful content
                            title_found = True
                            logger.debug(f"[PRODUCT] ✓ Found title: {text.strip()[:50]}")
                            break
                except:
                    continue

            # Element 2: Product Description or Details
            description_found = False
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
                        if text and len(text.strip()) > 10:  # Must have meaningful content
                            description_found = True
                            logger.debug(f"[PRODUCT] ✓ Found description")
                            break
                except:
                    continue

            # Element 3: Price
            price_found = False
            # Try structured data first (most reliable)
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
                    price_found = True
                    logger.debug(f"[PRODUCT] ✓ Found structured price: {structured_price}")
            except:
                pass

            # Fallback to class-based selectors
            if not price_found:
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
                            # Must contain currency or number
                            if any(c in text for c in ["$", "€", "£", "kr", "DKK", "SEK", "NOK"]) or \
                               any(char.isdigit() for char in text):
                                price_found = True
                                logger.debug(f"[PRODUCT] ✓ Found price: {text.strip()[:30]}")
                                break
                    except:
                        continue

            # Element 4: Add-to-cart/basket button
            add_to_cart_found = False
            for selector in settings.add_to_cart_selectors[:25]:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        # Check if visible
                        is_visible = await button.is_visible()
                        if is_visible:
                            add_to_cart_found = True
                            logger.debug("[PRODUCT] ✓ Found add-to-cart button")
                            break
                except:
                    continue

            await page.close()

            # Count how many indicators we found
            indicators = sum([title_found, description_found, price_found, add_to_cart_found])

            # Decision: Need at least 3 out of 4 indicators, OR 2 indicators + product URL pattern
            is_product = (indicators >= 3) or (indicators >= 2 and has_product_url_pattern)

            if is_product:
                logger.info(f"[PRODUCT] [OK] Valid product page ({indicators}/4 indicators, URL pattern: {has_product_url_pattern}) - title: {title_found}, desc: {description_found}, price: {price_found}, cart: {add_to_cart_found}")
            else:
                missing = []
                if not title_found: missing.append("title")
                if not description_found: missing.append("description")
                if not price_found: missing.append("price")
                if not add_to_cart_found: missing.append("add-to-cart")
                logger.debug(f"[PRODUCT] ✗ Not a valid product page ({indicators}/4 indicators, URL pattern: {has_product_url_pattern}) - Missing: {missing}")

            return is_product

        except PlaywrightTimeoutError:
            logger.debug("[PRODUCT] Timeout checking page")
            if page:
                try:
                    await page.close()
                except:
                    pass
            return False
        except Exception as e:
            logger.debug(f"[PRODUCT] Error checking page: {str(e)[:100]}")
            if page:
                try:
                    await page.close()
                except:
                    pass
            return False

    async def _discover_random_product(
        self,
        url: str,
        domain: str,
        base_url: str,
        max_attempts: int = 3
    ) -> Optional[str]:
        """
        Discover a random product page from the website.

        Strategy:
        1. Scan the provided URL for product links
        2. If none found, explore category/collection pages
        3. Score and filter candidates
        4. Randomly select from valid products (avoiding previously selected)
        5. Validate the selected product page

        Args:
            url: Starting URL to scan
            domain: Website domain
            base_url: Base URL of the site
            max_attempts: Maximum discovery attempts

        Returns:
            Random product page URL or None
        """
        for attempt in range(max_attempts):
            logger.info(f"[DISCOVERY] Attempt {attempt + 1}/{max_attempts}")

            page = None
            try:
                page = await self.browser.new_page()
                page.set_default_timeout(self.timeout)
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                # Wait for dynamic content and scroll to trigger lazy-loading
                try:
                    await page.wait_for_timeout(2000)  # Wait 2s for JavaScript
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    await page.wait_for_timeout(1000)  # Wait for lazy-load
                except Exception as e:
                    logger.debug(f"[DISCOVERY] Scroll/wait error: {e}")

                # Collect product link candidates
                candidates = await self._collect_product_candidates(page, base_url)

                if not candidates:
                    logger.info("[DISCOVERY] No candidates on main page, trying categories...")
                    # Try category pages
                    category_candidates = await self._explore_categories(page, base_url, domain)
                    candidates.extend(category_candidates)

                await page.close()
                page = None

                if not candidates:
                    logger.warning(f"[DISCOVERY] No product candidates found (attempt {attempt + 1})")
                    if attempt < max_attempts - 1:
                        continue
                    return None

                logger.info(f"[DISCOVERY] Found {len(candidates)} product candidates")

                # Score and filter candidates
                scored_candidates = self._score_and_filter_candidates(candidates, domain)

                if not scored_candidates:
                    logger.warning("[DISCOVERY] All candidates filtered out")
                    if attempt < max_attempts - 1:
                        continue
                    return None

                # Select random product (avoiding previously selected)
                selected_product = self._select_random_product(scored_candidates, domain)

                if not selected_product:
                    logger.warning("[DISCOVERY] No new products available")
                    if attempt < max_attempts - 1:
                        continue
                    return None

                # Validate the selected product
                logger.info(f"[DISCOVERY] Validating selected product: {selected_product}")
                if await self._is_product_page(selected_product):
                    # Mark as selected for future variety
                    self._mark_as_selected(domain, selected_product)
                    return selected_product
                else:
                    logger.debug("[DISCOVERY] Selected URL failed validation, retrying...")
                    if attempt < max_attempts - 1:
                        continue

            except Exception as e:
                logger.error(f"[DISCOVERY] Error: {str(e)[:200]}")
                logger.debug(traceback.format_exc())
                if page:
                    try:
                        await page.close()
                    except:
                        pass
                if attempt < max_attempts - 1:
                    continue

        return None

    async def _navigate_to_product(
        self,
        url: str,
        domain: str,
        base_url: str,
        max_depth: int = 5
    ) -> Optional[str]:
        """
        Navigate through categories to find a product page.

        NEW STRATEGY (improved for sites like matas.dk):
        1. Check if current URL is a product page
        2. If not, look for categories
        3. Select a random category and navigate to it
        4. Check for product listings (items with title + price)
        5. If product listings found, randomly select one and check if it's a product page
        6. If no product listings (might be sub-categories), go deeper into sub-categories
        7. Repeat until finding a valid product page

        Args:
            url: Starting URL
            domain: Website domain
            base_url: Base URL of the site
            max_depth: Maximum navigation depth

        Returns:
            Product page URL or None
        """
        current_url = url
        page = None

        try:
            page = await self.browser.new_page()
            page.set_default_timeout(self.timeout)

            for depth in range(max_depth):
                logger.info(f"[NAVIGATE] Depth {depth + 1}/{max_depth} - Current URL: {current_url}")

                await page.goto(current_url, wait_until="domcontentloaded", timeout=self.timeout)

                # Wait for dynamic content
                try:
                    await page.wait_for_timeout(2000)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    await page.wait_for_timeout(1000)
                except Exception as e:
                    logger.debug(f"[NAVIGATE] Scroll/wait error: {e}")

                # STEP 1: Check if current page is already a product page
                if await self._is_product_page(current_url):
                    logger.info(f"[NAVIGATE] [OK] Found product page at depth {depth + 1}")
                    self._mark_as_selected(domain, current_url)
                    return current_url

                # STEP 2: Not a product page - look for PRODUCT LISTINGS (items with title + price)
                logger.info(f"[NAVIGATE] Not a product page, looking for product listings...")

                product_listings = await self._find_product_listings(page)

                if product_listings:
                    # Found product listings! Select one randomly
                    logger.info(f"[NAVIGATE] Found {len(product_listings)} product listings")
                    selected_product = random.choice(product_listings)
                    logger.info(f"[NAVIGATE] Selected product: {selected_product[:80]}")
                    current_url = selected_product
                    # Continue to next depth to verify it's a product page
                    continue

                # STEP 3: No product listings found - look for CATEGORY/SUB-CATEGORY links
                logger.info(f"[NAVIGATE] No product listings, looking for categories/sub-categories...")

                category_links = await self._find_category_links(page, domain)

                if category_links:
                    # Found categories/sub-categories - select one randomly
                    logger.info(f"[NAVIGATE] Found {len(category_links)} category links")
                    selected_category = random.choice(category_links)
                    logger.info(f"[NAVIGATE] Selected category: {selected_category[:80]}")
                    current_url = selected_category
                    # Continue to next depth
                    continue

                # STEP 4: Nothing found at all
                logger.warning(f"[NAVIGATE] No product listings or categories found at depth {depth + 1}")
                return None

            logger.warning(f"[NAVIGATE] Max depth {max_depth} reached without finding product page")
            return None

        except Exception as e:
            logger.error(f"[NAVIGATE] Navigation error: {e}")
            return None

        finally:
            if page:
                await page.close()

    async def _find_product_listings(self, page: Page) -> List[str]:
        """
        Find product listings on current page.
        A product listing MUST have both title AND price.

        Returns:
            List of product URLs
        """
        product_urls = []

        try:
            # Find all elements that contain BOTH product info and price
            products = await page.evaluate("""() => {
                const results = [];

                // Look for common product listing containers
                const containerSelectors = [
                    '[class*="product"]',
                    '[class*="item"]',
                    '[data-product]',
                    'article',
                    'li[class*="product"]',
                    'div[class*="card"]'
                ];

                const containers = [];
                containerSelectors.forEach(sel => {
                    try {
                        document.querySelectorAll(sel).forEach(el => containers.push(el));
                    } catch(e) {}
                });

                containers.forEach(container => {
                    // Must have a link
                    const link = container.querySelector('a[href]');
                    if (!link || !link.href || !link.href.startsWith('http')) {
                        return;
                    }

                    // Must have price indicator
                    const priceKeywords = /kr|dkk|€|\\$|price|pris/i;
                    const priceElements = container.querySelectorAll('*');
                    let hasPrice = false;

                    for (let el of priceElements) {
                        const text = el.textContent || '';
                        if (priceKeywords.test(text) && /\\d+/.test(text)) {
                            hasPrice = true;
                            break;
                        }
                    }

                    // Must have some text content (product title/name)
                    const text = container.textContent || '';
                    const hasContent = text.trim().length > 20 && text.trim().length < 500;

                    if (hasPrice && hasContent && link.href) {
                        results.push(link.href);
                    }
                });

                return [...new Set(results)];
            }""")

            product_urls = products[:50]  # Limit to 50

        except Exception as e:
            logger.debug(f"[NAVIGATE] Error finding product listings: {e}")

        return product_urls

    async def _find_category_links(self, page: Page, domain: str) -> List[str]:
        """
        Find category/sub-category links on current page.

        Returns:
            List of category URLs
        """
        category_urls = []

        try:
            # Find navigation links, menu items, category links
            categories = await page.evaluate("""() => {
                const results = [];

                // Look for navigation/menu links
                const selectors = [
                    'nav a[href]',
                    '[class*="menu"] a[href]',
                    '[class*="category"] a[href]',
                    '[class*="nav"] a[href]',
                    '[role="navigation"] a[href]',
                    'header a[href]',
                    'a[class*="category"]',
                    'ul[class*="menu"] a',
                    'ul[class*="nav"] a'
                ];

                const links = new Set();

                selectors.forEach(sel => {
                    try {
                        document.querySelectorAll(sel).forEach(link => {
                            if (link.href && link.href.startsWith('http')) {
                                // Filter out: contact, about, policy, cart, checkout, account
                                const text = (link.textContent || '').toLowerCase();
                                const href = link.href.toLowerCase();
                                const exclude = ['kontakt', 'om', 'about', 'policy', 'privacy', 'cart', 'kurv', 'checkout', 'kassen', 'login', 'konto', 'account'];

                                if (!exclude.some(word => text.includes(word) || href.includes(word))) {
                                    links.add(link.href);
                                }
                            }
                        });
                    } catch(e) {}
                });

                return Array.from(links);
            }""")

            # Filter to same domain
            category_urls = [url for url in categories if domain in url][:30]

        except Exception as e:
            logger.debug(f"[NAVIGATE] Error finding category links: {e}")

        return category_urls

    async def _collect_product_candidates(self, page: Page, base_url: str) -> List[str]:
        """
        Collect potential product page URLs from the current page.

        Uses progressive selector strategy:
        1. High-confidence product URL patterns
        2. Product container patterns
        3. Semantic areas and general links

        Args:
            page: Playwright page object
            base_url: Base URL for resolving relative links

        Returns:
            List of candidate URLs
        """
        candidates = []

        # Strategy 1: Schema.org Product links (highest confidence)
        try:
            schema_products = await page.query_selector_all('[itemtype*="schema.org/Product"]')
            for elem in schema_products[:10]:
                link = await elem.query_selector("a[href]")
                if link:
                    href = await link.get_attribute("href")
                    if href and not href.startswith(("#", "javascript:", "mailto:")):
                        full_url = urljoin(base_url, href)
                        if full_url not in candidates:
                            candidates.append(full_url)
                            logger.debug(f"[COLLECT] Schema.org product: {full_url}")
        except:
            pass

        # Strategy 2: Product URL patterns in links
        product_href_selectors = [
            "a[href*='/product/']",
            "a[href*='/products/']",
            "a[href*='/p/']",
            "a[href*='/item/']",
            "a[href*='/vare/']",
            "a[href*='/catalogue/']",
            "a[href*='/catalog/']",
        ]

        for selector in product_href_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for elem in elements[:20]:  # Limit per selector
                    href = await elem.get_attribute("href")
                    if href and not href.startswith(("#", "javascript:", "mailto:")):
                        full_url = urljoin(base_url, href)
                        if full_url not in candidates:
                            candidates.append(full_url)
            except:
                pass

        # Strategy 3: Product container patterns (more aggressive)
        if len(candidates) < 10:
            container_selectors = [
                ".product-item a[href]",
                ".product-card a[href]",
                "[class*='product'] a[href]",
                "article a[href]",
                "[data-product-id] a[href]",
                "[class*='item'] a[href]",
                ".grid a[href]",
                "[class*='tile'] a[href]",
            ]

            for selector in container_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for elem in elements[:25]:
                        href = await elem.get_attribute("href")
                        if href and not href.startswith(("#", "javascript:", "mailto:")):
                            full_url = urljoin(base_url, href)
                            if full_url not in candidates:
                                candidates.append(full_url)
                except:
                    pass

        # Strategy 4: Look for links with product-related keywords in images
        if len(candidates) < 10:
            try:
                image_links = await page.query_selector_all("a:has(img)")
                for elem in image_links[:40]:
                    href = await elem.get_attribute("href")
                    if href and not href.startswith(("#", "javascript:", "mailto:")):
                        full_url = urljoin(base_url, href)
                        # Strict filtering - must not match non-product patterns
                        excluded_patterns = ["/blog", "/story", "/stories", "/gaver", "/gifts", "/influencer", "/inspiration", "/guide", "/campaign"]
                        if full_url not in candidates and not any(p in full_url.lower() for p in excluded_patterns):
                            # Must have reasonable path depth
                            if 3 <= full_url.count("/") <= 6:
                                candidates.append(full_url)
            except:
                pass

        logger.info(f"[COLLECT] Collected {len(candidates)} total candidates")
        return candidates

    async def _explore_categories(
        self,
        page: Page,
        base_url: str,
        domain: str
    ) -> List[str]:
        """
        Explore category/collection pages to find products.

        Args:
            page: Playwright page object (currently on homepage)
            base_url: Base URL of the site
            domain: Website domain

        Returns:
            List of product candidate URLs from categories
        """
        candidates = []

        # Find category/collection URLs - cast wider net
        category_selectors = [
            "nav a[href*='/category/']",
            "nav a[href*='/collection/']",
            "nav a[href*='/shop/']",
            "nav a[href*='/produkter/']",
            "nav a[href^='/']",  # Any navigation link
            "[class*='menu'] a[href^='/']",
            "[class*='nav'] a[href^='/']",
            "[class*='category'] a[href^='/']",
            "header a[href^='/']",  # Header links often lead to categories
        ]

        category_urls = []
        for selector in category_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for elem in elements[:8]:
                    href = await elem.get_attribute("href")
                    if href and not href.startswith(("#", "javascript:", "mailto:")):
                        full_url = urljoin(base_url, href)
                        # Filter out non-category URLs - be more restrictive
                        excluded = ["/about", "/contact", "/cart", "/checkout", "/gaver", "/gifts", "/story", "/stories", "/influencer", "/blog", "/inspiration", "/campaign"]
                        if not any(p in full_url.lower() for p in excluded):
                            # Must look like a category (reasonable depth, not too specific)
                            if full_url not in category_urls and 3 <= full_url.count("/") <= 5:
                                category_urls.append(full_url)
            except:
                pass

        if not category_urls:
            logger.debug("[CATEGORY] No category URLs found")
            return candidates

        logger.info(f"[CATEGORY] Found {len(category_urls)} category URLs, exploring...")

        # Randomly sample up to 5 categories (increased from 3)
        sample_size = min(5, len(category_urls))
        selected_categories = random.sample(category_urls, sample_size)

        for cat_url in selected_categories:
            try:
                cat_page = await self.browser.new_page()
                cat_page.set_default_timeout(10000)
                await cat_page.goto(cat_url, wait_until="domcontentloaded", timeout=10000)

                # Collect products from category page
                cat_candidates = await self._collect_product_candidates(cat_page, base_url)

                # Filter out obvious non-products from category results
                excluded_patterns = ["/stories", "/story", "/gaver", "/gifts", "/influencer", "/campaign", "/fast-lav-pris"]
                filtered_cat = [
                    url for url in cat_candidates
                    if not any(p in url.lower() for p in excluded_patterns)
                ]

                candidates.extend(filtered_cat)

                await cat_page.close()

                logger.info(f"[CATEGORY] Found {len(filtered_cat)} potential products in {cat_url}")

                # Stop early if we found enough candidates
                if len(candidates) >= 20:
                    logger.info(f"[CATEGORY] Found enough candidates ({len(candidates)}), stopping category exploration")
                    break

            except Exception as e:
                logger.debug(f"[CATEGORY] Error exploring {cat_url}: {str(e)[:100]}")
                continue

        return candidates

    def _score_and_filter_candidates(
        self,
        candidates: List[str],
        domain: str
    ) -> List[Tuple[str, float]]:
        """
        Score and filter product candidates.

        Scoring factors:
        - URL patterns (product/, item/, etc.)
        - Product ID patterns
        - Negative patterns (blog/, category/, etc.)

        Args:
            candidates: List of candidate URLs
            domain: Website domain

        Returns:
            List of (url, score) tuples, sorted by score descending
        """
        scored = []

        for url in candidates:
            score = 0.0
            url_lower = url.lower()

            # Positive patterns
            if any(p in url_lower for p in ["/product/", "/products/", "/p/", "/item/"]):
                score += 20
            elif any(p in url_lower for p in ["/vare/", "/catalogue/", "/catalog/"]):
                score += 15

            # Product ID pattern (strong indicator)
            if re.search(r"/\d{4,}", url) or re.search(r"[-_]\d{4,}", url):
                score += 15

            # Has hyphenated product name pattern (e.g., /brand-name/product-name-variant)
            # Common in modern e-commerce sites
            path_parts = url_lower.split('/')
            if len(path_parts) >= 2:
                last_part = path_parts[-1]
                # Check if last part looks like a product slug (multiple hyphens, reasonable length)
                if last_part.count('-') >= 2 and 10 <= len(last_part) <= 100:
                    score += 10

            # Negative patterns (disqualify)
            # Match both /pattern/, /pattern-, pattern/ at start/middle/end of path
            for pattern in settings.non_product_patterns:
                clean_pattern = pattern.strip('/')
                # Check if pattern appears anywhere in the URL path
                # Matches: /pattern/, /pattern-, -pattern/, -pattern-, /pattern (end of URL)
                if f"/{clean_pattern}/" in url_lower or \
                   f"/{clean_pattern}-" in url_lower or \
                   f"-{clean_pattern}/" in url_lower or \
                   f"-{clean_pattern}-" in url_lower or \
                   url_lower.endswith(f"/{clean_pattern}"):
                    score -= 100
                    logger.debug(f"[FILTER] Rejected {url} due to pattern: {pattern}")
                    break

            # Must have reasonable path depth
            if url.count("/") >= 3:
                score += 5

            # Add small randomness for variety
            score += random.uniform(0, 3)

            # Only keep candidates with positive scores
            if score > 0:
                scored.append((url, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"[FILTER] {len(scored)} candidates after filtering (removed {len(candidates) - len(scored)})")

        return scored

    def _select_random_product(
        self,
        scored_candidates: List[Tuple[str, float]],
        domain: str
    ) -> Optional[str]:
        """
        Select a random product from scored candidates, avoiding previously selected ones.

        Uses weighted random selection where higher-scored products have higher probability.

        Args:
            scored_candidates: List of (url, score) tuples
            domain: Website domain

        Returns:
            Selected product URL or None
        """
        if not scored_candidates:
            return None

        # Filter out previously selected URLs
        previously_selected = self._selected_products_cache.get(domain, set())
        new_candidates = [(url, score) for url, score in scored_candidates if url not in previously_selected]

        # If all were previously selected, reset and use all candidates
        if not new_candidates:
            logger.info("[SELECT] All candidates were previously selected, resetting cache")
            new_candidates = scored_candidates

        # Extract URLs and scores
        urls = [url for url, _ in new_candidates]
        scores = [score for _, score in new_candidates]

        # Convert scores to weights (ensure positive)
        min_score = min(scores)
        offset = abs(min_score) + 1 if min_score < 0 else 0
        weights = [score + offset for score in scores]

        # Weighted random selection (top 30% of candidates for quality)
        pool_size = max(1, int(len(new_candidates) * 0.3))
        pool = new_candidates[:pool_size]
        pool_urls = [url for url, _ in pool]
        pool_weights = weights[:pool_size]

        # Select one randomly
        selected = random.choices(pool_urls, weights=pool_weights, k=1)[0]

        logger.info(f"[SELECT] Selected from pool of {pool_size} candidates (out of {len(new_candidates)})")

        return selected

    def _mark_as_selected(self, domain: str, url: str):
        """
        Mark a URL as selected to ensure variety in future runs.

        Args:
            domain: Website domain
            url: Selected product URL
        """
        if domain not in self._selected_products_cache:
            self._selected_products_cache[domain] = set()

        self._selected_products_cache[domain].add(url)

        # Keep cache bounded (FIFO)
        if len(self._selected_products_cache[domain]) > self._max_cache_size_per_domain:
            cache_list = list(self._selected_products_cache[domain])
            self._selected_products_cache[domain] = set(cache_list[1:])

        logger.debug(f"[SELECT] Marked as selected (cache size: {len(self._selected_products_cache[domain])})")

    async def _detect_selectors(self, url: str) -> Dict[str, Optional[str]]:
        """
        Detect universal selectors on the product page.

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

            # Detect title
            title_patterns = ["//h1", "//h2", "//*[@class='title']"]
            for pattern in title_patterns:
                try:
                    elem = await page.query_selector(f"xpath={pattern}")
                    if elem:
                        selectors["title"] = pattern
                        logger.info(f"[DETECT] Title: {pattern}")
                        break
                except:
                    pass

            # Detect price
            price_patterns = [
                "//*[contains(@class, 'price') and not(contains(@class, 'old'))]",
                "//*[@itemprop='price']",
                "//*[contains(@class, 'product-price')]",
            ]
            for pattern in price_patterns:
                try:
                    elem = await page.query_selector(f"xpath={pattern}")
                    if elem:
                        selectors["price"] = pattern
                        logger.info(f"[DETECT] Price: {pattern}")
                        break
                except:
                    pass

            await page.close()

            detected_count = sum(1 for v in selectors.values() if v)
            logger.info(f"[DETECT] Detected {detected_count}/6 selectors")

        except Exception as e:
            logger.error(f"[DETECT] Error: {str(e)[:100]}")
            if page:
                try:
                    await page.close()
                except:
                    pass

        return selectors

    async def _check_robots_txt(self, base_url: str, url: str) -> Dict:
        """
        Check robots.txt for scraping permissions.

        Validates that critical paths (products, cart, checkout) are allowed.

        Args:
            base_url: Base URL of the website
            url: Current URL being analyzed

        Returns:
            Dictionary with robots.txt analysis results
        """
        robots_url = urljoin(base_url, "/robots.txt")
        logger.info(f"[ROBOTS.TXT] Checking {robots_url}")

        # Critical paths needed for scraping
        critical_paths = {
            "products": ["/product", "/products", "/catalogue", "/catalog", "/item", "/vare"],
            "cart": ["/cart", "/basket", "/kurv"],
            "checkout": ["/checkout", "/kasse", "/order"],
        }

        result = {
            "base_allowed": True,
            "message": "Allowed",
            "crawl_delay": 3,
            "blocked_paths": [],
            "allowed_paths": [],
            "warnings": [],
            "bot_protection_detected": False,
        }

        # Create log file
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d")
        robots_log = log_dir / f"robots_txt_{timestamp}.log"

        def log_to_file(msg: str):
            with open(robots_log, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")

        try:
            log_to_file(f"{'='*80}")
            log_to_file(f"CHECKING: {robots_url}")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(robots_url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        content = await response.text()
                        logger.info(f"[ROBOTS.TXT] Fetched ({len(content)} bytes)")
                        log_to_file(f"STATUS: 200 OK\nCONTENT:\n{content}\n")

                        # Parse robots.txt
                        rp = urllib.robotparser.RobotFileParser()
                        rp.parse(content.splitlines())

                        # Check critical paths
                        log_to_file("PATH ANALYSIS:")
                        for category, paths in critical_paths.items():
                            for path in paths:
                                test_url = urljoin(base_url, path)
                                if rp.can_fetch("*", test_url):
                                    result["allowed_paths"].append(path)
                                    log_to_file(f"  ✓ ALLOWED: {path}")
                                else:
                                    result["blocked_paths"].append(path)
                                    log_to_file(f"  ✗ BLOCKED: {path}")

                        # Determine if scraping is allowed
                        if result["blocked_paths"]:
                            result["base_allowed"] = False
                            result["message"] = f"Critical paths blocked: {', '.join(result['blocked_paths'])}"
                            logger.error(f"[ROBOTS.TXT] *** {result['message']} ***")
                            log_to_file(f"RESULT: ⛔ SCRAPING NOT ALLOWED")
                        else:
                            logger.info("[ROBOTS.TXT] [OK] All critical paths allowed")
                            log_to_file("RESULT: ✅ SCRAPING ALLOWED")

                        # Check crawl delay
                        crawl_delay = rp.crawl_delay("*")
                        if crawl_delay:
                            result["crawl_delay"] = int(crawl_delay)
                            logger.info(f"[ROBOTS.TXT] Crawl delay: {crawl_delay}s")
                            log_to_file(f"CRAWL DELAY: {crawl_delay}s")

                    elif response.status == 404:
                        logger.info("[ROBOTS.TXT] No robots.txt (404) - allowed")
                        log_to_file("STATUS: 404 - No robots.txt")
                        result["message"] = "No robots.txt"

                    elif response.status == 403:
                        logger.warning("[ROBOTS.TXT] 403 - Bot protection detected")
                        log_to_file("STATUS: 403 - Bot protection")
                        result["bot_protection_detected"] = True
                        result["message"] = "Bot protection detected"

                    else:
                        logger.warning(f"[ROBOTS.TXT] Status {response.status}")
                        log_to_file(f"STATUS: {response.status}")
                        result["message"] = f"Status {response.status}"

        except Exception as e:
            logger.warning(f"[ROBOTS.TXT] Error: {e}")
            log_to_file(f"ERROR: {e}")
            result["message"] = f"Error: {e}"

        log_to_file(f"{'='*80}\n")
        return result

    async def _check_bot_protection(self, url: str) -> Dict:
        """
        Check for bot protection mechanisms.

        Args:
            url: URL to check

        Returns:
            Dictionary with bot protection information
        """
        # Simplified implementation - can be enhanced with actual detection logic
        return {
            "detected": False,
            "types": [],
            "confidence": "low"
        }

    # Legacy compatibility methods (kept for backward compatibility if needed)
    async def discover_product_url(self, url: str, max_retries: int = 2) -> Optional[str]:
        """Legacy method for backward compatibility."""
        parsed = urlparse(url)
        domain = parsed.netloc
        base_url = f"{parsed.scheme}://{domain}"
        return await self._find_product_page(url, domain, base_url)

    async def detect_universal_selectors(self, url: str) -> Dict[str, Optional[str]]:
        """Legacy method for backward compatibility."""
        return await self._detect_selectors(url)
