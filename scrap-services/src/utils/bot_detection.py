"""Bot detection and robots.txt checking utilities."""
import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse, urljoin
import requests
from robotexclusionrulesparser import RobotExclusionRulesParser
from src.utils.logger import logger


class BotDetector:
    """Detect bot protection and check robots.txt compliance."""
    
    def __init__(self, user_agent: str = "ScraperBot/1.0"):
        """
        Initialize bot detector.
        
        Args:
            user_agent: User agent string for robots.txt checking
        """
        self.user_agent = user_agent
        self.robot_parser = RobotExclusionRulesParser()
    
    def check_robots_txt(self, url: str) -> Tuple[bool, str]:
        """
        Check if scraping is allowed by robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            Tuple of (is_allowed, message)
        """
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            robots_url = urljoin(base_url, "/robots.txt")
            
            logger.info(f"Checking robots.txt at: {robots_url}")
            
            # Fetch robots.txt
            response = requests.get(robots_url, timeout=10)
            
            if response.status_code == 404:
                logger.info("No robots.txt found - scraping allowed by default")
                return True, "No robots.txt found (allowed by default)"
            
            if response.status_code != 200:
                logger.warning(f"Could not fetch robots.txt: HTTP {response.status_code}")
                return True, f"robots.txt fetch failed (HTTP {response.status_code})"
            
            # Parse robots.txt
            self.robot_parser.parse(response.text)
            
            # Check if URL is allowed for our user agent
            is_allowed = self.robot_parser.is_allowed(self.user_agent, url)
            
            if is_allowed:
                logger.info(f"✅ Scraping allowed by robots.txt for: {url}")
                return True, "Scraping allowed by robots.txt"
            else:
                logger.warning(f"⚠️ Scraping DISALLOWED by robots.txt for: {url}")
                return False, "Scraping disallowed by robots.txt"
        
        except requests.exceptions.Timeout:
            logger.warning("robots.txt request timed out")
            return True, "robots.txt timeout (proceeding with caution)"
        
        except Exception as e:
            logger.error(f"Error checking robots.txt: {e}")
            return True, f"robots.txt check failed: {str(e)}"
    
    def detect_bot_protection(self, page_source: str, url: str) -> Dict[str, any]:
        """
        Detect common bot protection mechanisms in page source.
        
        Args:
            page_source: HTML source of the page
            url: URL being accessed
            
        Returns:
            Dictionary with detection results
        """
        detections = {
            "has_protection": False,
            "protection_types": [],
            "confidence": "low",
            "details": []
        }
        
        # Check for Cloudflare
        if self._detect_cloudflare(page_source):
            detections["has_protection"] = True
            detections["protection_types"].append("Cloudflare")
            detections["details"].append("Cloudflare protection detected")
            logger.warning("🛡️ Cloudflare bot protection detected")
        
        # Check for CAPTCHA
        captcha_type = self._detect_captcha(page_source)
        if captcha_type:
            detections["has_protection"] = True
            detections["protection_types"].append(f"CAPTCHA ({captcha_type})")
            detections["details"].append(f"{captcha_type} CAPTCHA detected")
            logger.warning(f"🛡️ {captcha_type} CAPTCHA detected")
        
        # Check for DataDome
        if self._detect_datadome(page_source):
            detections["has_protection"] = True
            detections["protection_types"].append("DataDome")
            detections["details"].append("DataDome protection detected")
            logger.warning("🛡️ DataDome bot protection detected")
        
        # Check for PerimeterX
        if self._detect_perimeterx(page_source):
            detections["has_protection"] = True
            detections["protection_types"].append("PerimeterX")
            detections["details"].append("PerimeterX protection detected")
            logger.warning("🛡️ PerimeterX bot protection detected")
        
        # Check for access denied messages
        if self._detect_access_denied(page_source):
            detections["has_protection"] = True
            detections["protection_types"].append("Access Denied")
            detections["details"].append("Access denied message found")
            logger.warning("🛡️ Access denied message detected")
        
        # Check for empty/minimal content (possible bot blocking)
        if self._detect_empty_content(page_source):
            detections["protection_types"].append("Minimal Content")
            detections["details"].append("Suspiciously minimal page content")
            logger.warning("⚠️ Page has minimal content - possible bot blocking")
        
        # Set confidence level
        if len(detections["protection_types"]) >= 2:
            detections["confidence"] = "high"
        elif len(detections["protection_types"]) == 1:
            detections["confidence"] = "medium"
        
        # Log summary
        if detections["has_protection"]:
            logger.error(f"🚫 Bot protection detected on {url}: {', '.join(detections['protection_types'])}")
        else:
            logger.info(f"✅ No obvious bot protection detected on {url}")
        
        return detections
    
    def _detect_cloudflare(self, page_source: str) -> bool:
        """Detect Cloudflare protection."""
        cloudflare_patterns = [
            r'Checking your browser',
            r'cloudflare',
            r'cf-ray',
            r'__cf_bm',
            r'cf_clearance',
            r'Cloudflare Ray ID'
        ]
        return any(re.search(pattern, page_source, re.IGNORECASE) for pattern in cloudflare_patterns)
    
    def _detect_captcha(self, page_source: str) -> Optional[str]:
        """Detect CAPTCHA presence and type."""
        if re.search(r'g-recaptcha|recaptcha', page_source, re.IGNORECASE):
            return "reCAPTCHA"
        if re.search(r'h-captcha|hcaptcha', page_source, re.IGNORECASE):
            return "hCaptcha"
        if re.search(r'captcha', page_source, re.IGNORECASE):
            return "Generic CAPTCHA"
        return None
    
    def _detect_datadome(self, page_source: str) -> bool:
        """Detect DataDome protection."""
        datadome_patterns = [
            r'datadome',
            r'dd_cookie',
            r'DataDome'
        ]
        return any(re.search(pattern, page_source, re.IGNORECASE) for pattern in datadome_patterns)
    
    def _detect_perimeterx(self, page_source: str) -> bool:
        """Detect PerimeterX protection."""
        px_patterns = [
            r'perimeterx',
            r'_px\d*',
            r'PerimeterX'
        ]
        return any(re.search(pattern, page_source, re.IGNORECASE) for pattern in px_patterns)
    
    def _detect_access_denied(self, page_source: str) -> bool:
        """Detect access denied messages."""
        denied_patterns = [
            r'access\s+denied',
            r'access\s+blocked',
            r'you\s+have\s+been\s+blocked',
            r'unusual\s+traffic',
            r'automated\s+queries',
            r'detected\s+as\s+(a\s+)?robot',
            r'bot\s+detected',
            r'please\s+verify\s+you\s+are\s+(a\s+)?human',
            r'this\s+request\s+has\s+been\s+blocked'
        ]
        return any(re.search(pattern, page_source, re.IGNORECASE) for pattern in denied_patterns)
    
    def _detect_empty_content(self, page_source: str) -> bool:
        """Detect suspiciously empty content."""
        # Remove HTML tags and whitespace
        text_content = re.sub(r'<[^>]+>', '', page_source)
        text_content = re.sub(r'\s+', ' ', text_content).strip()
        
        # If page has very little text content, it might be blocked
        return len(text_content) < 200
    
    def get_crawl_delay(self, base_url: str) -> Optional[int]:
        """
        Get crawl delay from robots.txt.
        
        Args:
            base_url: Base URL of the website
            
        Returns:
            Crawl delay in seconds, or None if not specified
        """
        try:
            robots_url = urljoin(base_url, "/robots.txt")
            response = requests.get(robots_url, timeout=10)
            
            if response.status_code == 200:
                # Look for Crawl-delay directive
                match = re.search(r'Crawl-delay:\s*(\d+)', response.text, re.IGNORECASE)
                if match:
                    delay = int(match.group(1))
                    logger.info(f"Crawl-delay specified in robots.txt: {delay} seconds")
                    return delay
            
            return None
        
        except Exception as e:
            logger.warning(f"Could not get crawl delay: {e}")
            return None
