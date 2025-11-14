"""Data schemas for service communication (Kafka-ready)."""
from .messages import (
    AnalysisResult,
    ScrapedProduct,
    ProcessedProduct,
    ShippingProvider
)

__all__ = [
    "AnalysisResult",
    "ScrapedProduct",
    "ProcessedProduct",
    "ShippingProvider"
]
