"""Utility functions for data extraction using XPath and regex."""
import re
from typing import Optional, Tuple, Dict, Any


class DataExtractor:
    """
    Extract and parse data from web elements.

    Provides utility methods for extracting structured data from HTML elements,
    including price extraction, text normalization, and delivery time parsing.
    Handles multiple formats and currencies for international e-commerce sites.
    """

    @staticmethod
    def extract_price_with_regex(text: str) -> Optional[Tuple[float, str]]:
        """
        Extract price and currency from text using regex.

        Args:
            text: Text containing price information

        Returns:
            Tuple of (price, currency) or None if not found
        """
        if not text:
            return None

        # Remove whitespace and normalize
        text = text.strip().replace("\n", " ").replace("\r", "")

        # Pattern 1: Currency symbol before number (e.g., $99.99, €49,95, kr99)
        # Use word boundary for 'kr' to avoid matching 'r' from words like 'lager', 'Kloster'
        pattern1 = r"([€$£¥])\s*(\d+[.,]\d+|\d+)"
        match = re.search(pattern1, text)
        if match:
            currency_map = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY"}
            symbol = match.group(1)
            price_str = match.group(2).replace(",", ".")
            return float(price_str), currency_map.get(symbol, symbol)

        # Pattern 2: Number before currency code (e.g., 99.99 EUR, 49,95 DKK, 39 kr, 0 kr, 19 kr.)
        # Handle Danish 'kr' with optional period and various formats
        # Use word boundary or specific delimiter to avoid matching parts of addresses
        pattern2 = r"(\d+[.,]\d+|\d+)\s*(?:kr\.?|DKK|EUR|USD|GBP|SEK|NOK)(?:\s|$|[^\w])"
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(",", ".")
            # Extract currency part - handle "kr" with optional period
            currency_match = re.search(r"(\d+[.,]\d+|\d+)\s*(kr\.?|DKK|EUR|USD|GBP|SEK|NOK)", text, re.IGNORECASE)
            if currency_match:
                currency_part = currency_match.group(2).upper().replace(".", "")
                if currency_part == "KR":
                    currency = "DKK"
                else:
                    currency = currency_part
                return float(price_str), currency

        # Pattern 3: Just numbers with decimal (assume DKK for Danish sites)
        # Skip if it looks like a postal code pattern (number followed by comma and 4 digits)
        if not re.search(r"\d+,\s*\d{4}", text):
            pattern3 = r"(\d+[.,]\d+|\d+)"
            match = re.search(pattern3, text)
            if match:
                price_str = match.group(1).replace(",", ".")
                return float(price_str), "DKK"

        return None

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text by removing extra whitespace and special characters.

        Args:
            text: Text to normalize

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text)

        # Trim
        text = text.strip()

        return text

    @staticmethod
    def extract_delivery_time_with_regex(text: str) -> Optional[str]:
        """
        Extract delivery time information using regex.
        Enhanced to handle more formats and edge cases.

        Args:
            text: Text containing delivery information

        Returns:
            Delivery time string or None
        """
        if not text:
            return None

        text_lower = text.lower()

        # Pattern for delivery time (e.g., "2-3 days", "1-2 business days", "Next day")
        # Enhanced for Danish: "1-4 hverdage", "Få leveret fra i morgen", "Få leveret i dag"
        patterns = [
            # Danish phrases for today/tomorrow delivery
            (r"i\s+dag", "0 days"),  # "i dag" = today = 0 days
            (r"samme\s+dag", "0 days"),  # "samme dag" = same day = 0 days
            (r"fra\s+i\s+morgen", "1 day"),  # "fra i morgen" = from tomorrow = 1 day
            (r"i\s+morgen", "1 day"),  # "i morgen" = tomorrow = 1 day
            (r"næste\s+dag", "1 day"),  # "næste dag" = next day = 1 day
            
            # Standard delivery time ranges
            (r"(\d+[-–]\d+)\s*hverdage?", None),  # Danish: "1-4 hverdage"
            (r"(\d+[-–]\d+)\s*arbejdsdage?", None),  # Danish: "2-3 arbejdsdage"
            (r"(\d+)\s*hverdage?", None),  # Danish: "3 hverdage"
            (r"(\d+)\s*arbejdsdage?", None),  # Danish: "2 arbejdsdage"
            (r"(\d+[-–]\d+)\s*dage", None),  # Danish: "2-3 dage"
            (r"(\d+)\s*dage", None),  # Danish: "3 dage"
            
            # With prepositions
            (r"inden\s+for\s+(\d+[-–]\d+)\s*hverdage?", None),  # "inden for 1-4 hverdage"
            (r"om\s+(\d+[-–]\d+)\s*hverdage?", None),  # "om 2-3 hverdage"
            (r"på\s+(\d+[-–]\d+)\s*hverdage?", None),  # "på 1-2 hverdage"
            (r"ca\.?\s*(\d+[-–]\d+)\s*hverdage?", None),  # "ca. 2-3 hverdage"
            
            # English patterns
            (r"(\d+[-–]\d*)\s*(business\s*)?days?", None),  # English: "2-3 business days"
            (r"within\s+(\d+[-–]\d+)\s*(business\s*)?days?", None),  # "within 2-3 days"
            (r"in\s+(\d+[-–]\d+)\s*(business\s*)?days?", None),  # "in 2-3 days"
            
            # Special cases
            (r"next\s*day", "1 day"),  # "next day"
            (r"same\s*day", "0 days"),  # "same day"
            (r"express", "1-2 days"),  # "express" usually means 1-2 days
            (r"hurtig\s*levering", "1-2 days"),  # Danish: "hurtig levering" = fast delivery
            
            # Hours-based delivery
            (r"(\d+[-–]\d+)\s*(timer|hours?)", None),  # "24-48 timer" or "24 hours"
            (r"inden\s+(\d+)\s*(timer|hours?)", None),  # "inden 24 timer"
        ]

        for pattern_info in patterns:
            if isinstance(pattern_info, tuple):
                pattern, fixed_value = pattern_info
            else:
                pattern, fixed_value = pattern_info, None

            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                if fixed_value:
                    return fixed_value
                # Return the matched group, with some cleanup
                matched = match.group(1).strip()
                # Normalize dash characters
                matched = matched.replace("–", "-")
                return matched

        return None

    @staticmethod
    def validate_product_data(data: Dict[str, Any]) -> bool:
        """
        Validate that product data is complete and valid.

        Args:
            data: Product data dictionary

        Returns:
            True if valid, False otherwise
        """
        required_fields = ["title", "price", "currency", "url", "source_website"]

        # Check required fields exist
        if not all(field in data and data[field] for field in required_fields):
            return False

        # Validate price is positive
        if not isinstance(data["price"], (int, float)) or data["price"] <= 0:
            return False

        # Validate title is not too short
        if len(data["title"]) < 3:
            return False

        return True
