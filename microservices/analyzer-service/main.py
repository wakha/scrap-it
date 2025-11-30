"""Analyzer Service - Microservice Entry Point

This service:
1. Receives URLs via HTTP API endpoint
2. Analyzes websites for scrapability
3. Publishes AnalysisResult to Kafka 'analysis-results' topic
4. Exposes Prometheus metrics
"""
import os
import sys
import logging
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.schemas import AnalysisResult
from shared.kafka_client import KafkaProducerClient
from shared.metrics import (
    messages_produced, service_requests, service_duration,
    start_metrics_server
)
from analyzer import AnalyzerService

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = 'analysis-results'
SERVICE_NAME = 'analyzer-service'
SERVICE_PORT = int(os.getenv('SERVICE_PORT', '8001'))
METRICS_PORT = int(os.getenv('METRICS_PORT', '9001'))

# FastAPI app
app = FastAPI(title="Analyzer Service", version="1.0.0")

# Kafka producer (initialized on startup)
kafka_producer: Optional[KafkaProducerClient] = None


class AnalyzeRequest(BaseModel):
    """Request model for analysis."""
    url: str
    product_path: Optional[str] = None
    checkout_path: Optional[str] = None
    auto_discover: bool = True


class AnalyzeResponse(BaseModel):
    """Response model for analysis."""
    request_id: str
    status: str
    message: str
    analysis: Optional[dict] = None


@app.on_event("startup")
async def startup_event():
    """Initialize Kafka producer and metrics server on startup."""
    global kafka_producer
    
    try:
        # Start Prometheus metrics server
        start_metrics_server(METRICS_PORT)
        logger.info(f"Metrics server started on port {METRICS_PORT}")
        
        # Initialize Kafka producer
        kafka_producer = KafkaProducerClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            client_id=SERVICE_NAME
        )
        logger.info(f"{SERVICE_NAME} started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    if kafka_producer:
        kafka_producer.close()
    logger.info(f"{SERVICE_NAME} shutdown complete")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": SERVICE_NAME,
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "kafka_connected": kafka_producer is not None
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_website(request: AnalyzeRequest):
    """Analyze a website and publish results to Kafka.
    
    Args:
        request: Analysis request with URL and options
        
    Returns:
        Response with request ID and status
    """
    request_id = str(uuid.uuid4())
    start_time = datetime.now()
    
    try:
        logger.info(f"[{request_id}] Analyzing: {request.url}")
        
        # Perform analysis
        async with AnalyzerService() as analyzer:
            with service_duration.labels(
                service=SERVICE_NAME,
                operation='analyze'
            ).time():
                analysis: AnalysisResult = await analyzer.analyze_website(
                    url=request.url,
                    product_path=request.product_path,
                    checkout_path=request.checkout_path,
                    auto_discover=request.auto_discover
                )
        
        # Add request ID for tracing
        analysis.request_id = request_id
        
        # Publish to Kafka
        message = analysis.model_dump(mode='json')
        success = kafka_producer.send(
            topic=KAFKA_TOPIC,
            message=message,
            key=analysis.domain
        )
        
        if success:
            messages_produced.labels(
                service=SERVICE_NAME,
                topic=KAFKA_TOPIC
            ).inc()
            
            service_requests.labels(
                service=SERVICE_NAME,
                status='success'
            ).inc()
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"[{request_id}] Analysis complete - "
                f"can_scrape: {analysis.can_scrape}, duration: {duration:.2f}s"
            )
            
            return AnalyzeResponse(
                request_id=request_id,
                status="success",
                message="Analysis published to Kafka",
                analysis=message
            )
        else:
            raise Exception("Failed to publish to Kafka")
            
    except Exception as e:
        service_requests.labels(
            service=SERVICE_NAME,
            status='error'
        ).inc()
        
        logger.error(f"[{request_id}] Analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    logger.info(f"Starting {SERVICE_NAME} on port {SERVICE_PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SERVICE_PORT,
        log_level="info"
    )
