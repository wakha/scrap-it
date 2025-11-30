"""API Gateway - Unified Entry Point for Microservices

This service:
1. Provides unified REST API for external clients
2. Routes requests to appropriate microservices
3. Handles authentication and rate limiting
4. Aggregates responses from multiple services
5. Exposes Prometheus metrics
"""
import os
import sys
import logging
import uuid
from typing import Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import uvicorn

# Load environment variables only when running locally (not in Docker)
if not os.getenv('RUNNING_IN_DOCKER'):
    env_path = Path(__file__).parent.parent / '.env'
    env_local_path = Path(__file__).parent.parent / '.env.local'
    
    if env_local_path.exists():
        load_dotenv(dotenv_path=env_local_path, override=True)
    elif env_path.exists():
        load_dotenv(dotenv_path=env_path)

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.metrics import service_requests, service_duration, start_metrics_server

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
SERVICE_NAME = 'api-gateway'
SERVICE_PORT = int(os.getenv('SERVICE_PORT', '8000'))
METRICS_PORT = int(os.getenv('METRICS_PORT', '9000'))
API_KEY = os.getenv('API_KEY', 'your-api-key-here')

# Microservice URLs
ANALYZER_SERVICE_URL = os.getenv('ANALYZER_SERVICE_URL', 'http://localhost:8001')

# FastAPI app
app = FastAPI(
    title="Scraper API Gateway",
    description="Unified API for web scraping microservices",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    """Request model for initiating a scrape."""
    url: str
    product_path: Optional[str] = None
    checkout_path: Optional[str] = None
    auto_discover: bool = True


class ScrapeResponse(BaseModel):
    """Response model for scrape initiation."""
    request_id: str
    status: str
    message: str


def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key from header."""
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include X-API-Key header."
        )
    return x_api_key


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    try:
        start_metrics_server(METRICS_PORT)
        logger.info(f"Metrics server started on port {METRICS_PORT}")
        logger.info(f"{SERVICE_NAME} started successfully")
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": SERVICE_NAME,
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "scrape": "/api/v1/scrape",
            "health": "/health",
            "metrics": f"http://localhost:{METRICS_PORT}/metrics"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/v1/scrape", response_model=ScrapeResponse)
async def initiate_scrape(
    request: ScrapeRequest,
    x_api_key: str = Header(None)
):
    """Initiate a scraping job.
    
    This endpoint forwards the request to the Analyzer service,
    which kicks off the entire pipeline.
    
    Args:
        request: Scrape request parameters
        x_api_key: API key for authentication
        
    Returns:
        Response with request ID and status
    """
    # Verify API key
    verify_api_key(x_api_key)
    
    request_id = str(uuid.uuid4())
    
    try:
        logger.info(f"[{request_id}] Initiating scrape for: {request.url}")
        
        # Forward to Analyzer service
        async with httpx.AsyncClient() as client:
            with service_duration.labels(
                service=SERVICE_NAME,
                operation='forward_to_analyzer'
            ).time():
                response = await client.post(
                    f"{ANALYZER_SERVICE_URL}/analyze",
                    json=request.model_dump(),
                    timeout=60.0
                )
            
            if response.status_code == 200:
                service_requests.labels(
                    service=SERVICE_NAME,
                    status='success'
                ).inc()
                
                logger.info(f"[{request_id}] Scrape initiated successfully")
                
                return ScrapeResponse(
                    request_id=request_id,
                    status="processing",
                    message="Scraping job initiated. Results will be available in Kafka topics."
                )
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Analyzer service error: {response.text}"
                )
                
    except httpx.RequestError as e:
        service_requests.labels(
            service=SERVICE_NAME,
            status='error'
        ).inc()
        logger.error(f"[{request_id}] Failed to connect to Analyzer service: {e}")
        raise HTTPException(
            status_code=503,
            detail="Analyzer service unavailable"
        )
    except Exception as e:
        service_requests.labels(
            service=SERVICE_NAME,
            status='error'
        ).inc()
        logger.error(f"[{request_id}] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/status/{request_id}")
async def get_scrape_status(
    request_id: str,
    x_api_key: str = Header(None)
):
    """Get status of a scraping job.
    
    This would query a status service or database to get the current
    state of the scraping pipeline.
    """
    verify_api_key(x_api_key)
    
    # TODO: Implement status tracking service
    return {
        "request_id": request_id,
        "status": "not_implemented",
        "message": "Status tracking service not yet implemented"
    }


if __name__ == "__main__":
    logger.info(f"Starting {SERVICE_NAME} on port {SERVICE_PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SERVICE_PORT,
        log_level="info"
    )
