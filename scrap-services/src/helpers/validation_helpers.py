"""Validation helper functions."""
from typing import Optional


def is_valid_title(text: Optional[str], min_length: int = 5) -> bool:
    """Check if title text is valid.

    Args:
        text: The title text to validate
        min_length: Minimum required length

    Returns:
        True if valid, False otherwise
    """
    return text is not None and len(text.strip()) > min_length


def is_valid_description(text: Optional[str], min_length: int = 10) -> bool:
    """Check if description text is valid.

    Args:
        text: The description text to validate
        min_length: Minimum required length

    Returns:
        True if valid, False otherwise
    """
    return text is not None and len(text.strip()) > min_length


def contains_currency_or_number(text: str) -> bool:
    """Check if text contains currency symbols or numbers.

    Args:
        text: Text to check

    Returns:
        True if contains currency or numbers, False otherwise
    """
    currency_symbols = ["$", "€", "£", "kr", "DKK", "SEK", "NOK"]
    has_currency = any(symbol in text for symbol in currency_symbols)
    has_number = any(char.isdigit() for char in text)
    return has_currency or has_number


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
