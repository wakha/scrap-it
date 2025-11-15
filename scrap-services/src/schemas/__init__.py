"""Data schemas for service communication (Kafka-ready).

Pydantic models that serve as data transfer objects (DTOs) between services.
All schemas are JSON-serializable and suitable for message queue communication.
"""
from .messages import AnalysisResult, ScrapedProduct, ProcessedProduct, ShippingProvider

__all__ = ["AnalysisResult", "ScrapedProduct", "ProcessedProduct", "ShippingProvider"]
