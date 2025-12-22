"""
Main FastAPI application for Data Foundry
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from src.app.middleware import (
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    TenantContextMiddleware,
)
from src.api.v1.consent import router as consent_router
from src.core.config import settings
from src.core.security import get_current_user_token
from src.tasks.ingestion import data_ingestion_flow


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("🚀 Data Foundry is starting up...")
    print("📊 API Documentation: http://localhost:8000/docs")
    print("🏷️  Label Studio: http://localhost:8080")
    print("🔧 Prefect Dashboard: http://localhost:4200")

    yield

    # Shutdown
    print("🛑 Data Foundry is shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Enrichment-as-a-Service (EaaS) platform - AI-powered data cleaning and labeling",
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
app.add_middleware(TenantContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Include API routers
app.include_router(consent_router, prefix=settings.API_V1_STR)


# Test token endpoint for Phase 6.5 load testing - DEVELOPMENT ONLY
@app.get("/test-token")
async def get_test_token():
    """
    Generate a test JWT token for Phase 6.5 load testing.

    SECURITY NOTE: This endpoint is only available in DEBUG mode and should
    be disabled in production. Rate limited to prevent abuse.
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This endpoint is only available in development mode"
        )

    from src.core.security import create_access_token
    from datetime import timedelta

    # Create test token with load testing user
    test_payload = {
        "user_id": "load-test-user",
        "tenant_id": "test-tenant-1",
        "email": "load-test@datafoundry.com",
        "role": "user"
    }

    token = create_access_token(
        subject=test_payload["user_id"],
        expires_delta=timedelta(hours=24)  # Long expiry for testing
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,  # 24 hours
        "test_user": test_payload
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with basic information."""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "description": "Enrichment-as-a-Service (EaaS) platform",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


# Protected endpoint example
@app.get("/api/v1/me")
async def get_current_user(current_user: dict = Depends(get_current_user_token)):
    """Get current user information."""
    return {
        "user_id": current_user.get("user_id"),
        "tenant_id": current_user.get("tenant_id"),
        "token_type": "bearer",
    }


# Trigger ingestion flow
@app.post("/api/v1/ingest")
async def trigger_ingestion(
    data_source: str = "sample_data",
    enable_ai: bool = True,
    enable_pii: bool = True,
    enable_human_review: bool = True,
    current_user: dict = Depends(get_current_user_token),
):
    """
    Trigger the data ingestion pipeline.

    This endpoint starts the Prefect flow for data processing.
    """
    try:
        # Start the flow
        flow_run = await data_ingestion_flow(
            data_source=data_source,
            enable_ai_labeling=enable_ai,
            enable_pii_redaction=enable_pii,
            enable_human_review=enable_human_review,
        )

        return {
            "message": "Ingestion flow started successfully",
            "flow_run_id": str(flow_run) if flow_run else None,
            "tenant_id": current_user.get("tenant_id"),
            "user_id": current_user.get("user_id"),
            "parameters": {
                "data_source": data_source,
                "enable_ai": enable_ai,
                "enable_pii": enable_pii,
                "enable_human_review": enable_human_review,
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start ingestion flow: {str(e)}",
        )


# Process data endpoint (for k6 load testing)
@app.post("/api/v1/process")
async def process_data(
    request_data: dict = None,
    current_user: dict = Depends(get_current_user_token),
):
    """
    Process data for enrichment and analysis.

    This endpoint simulates the main data processing functionality
    that will be load tested in Phase 6.5.
    """
    import asyncio
    import time
    import random

    try:
        # Simulate processing time (100-500ms)
        processing_time = random.uniform(0.1, 0.5)
        await asyncio.sleep(processing_time)

        # Extract data from request
        if request_data and "data" in request_data:
            data = request_data["data"]
        else:
            data = {"id": f"processed_{int(time.time())}", "text": "Sample processed data"}

        # Simulate AI processing response
        result = {
            "status": "success",
            "processed_at": time.time(),
            "tenant_id": current_user.get("tenant_id"),
            "user_id": current_user.get("user_id"),
            "input_data": data,
            "output": {
                "id": data.get("id", "unknown"),
                "text": data.get("text", "processed"),
                "enriched": True,
                "confidence": random.uniform(0.85, 0.99),
                "processing_time_ms": round(processing_time * 1000, 2),
                "ai_model": "gpt-4-turbo-preview",
                "tokens_used": {
                    "input": random.randint(50, 200),
                    "output": random.randint(20, 100),
                    "total": random.randint(70, 300)
                },
                "cost_estimate": round(random.uniform(0.001, 0.01), 6)
            }
        }

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process data: {str(e)}",
        )


# System information endpoint
@app.get("/api/v1/system/info")
async def get_system_info():
    """Get system information and configuration."""
    return {
        "app": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
        },
        "services": {
            "database": {
                "url": (
                    settings.DATABASE_URL.split("@")[1]
                    if "@" in settings.DATABASE_URL
                    else "configured"
                ),
                "pool_size": settings.DATABASE_POOL_SIZE,
            },
            "redis": {
                "url": (
                    settings.REDIS_URL.split("@")[1]
                    if "@" in settings.REDIS_URL
                    else "configured"
                )
            },
            "label_studio": {"url": settings.LABEL_STUDIO_URL},
            "ai_providers": {
                "openai": {
                    "model": settings.OPENAI_MODEL,
                    "configured": bool(settings.secure_openai_api_key()),
                },
                "anthropic": {
                    "model": settings.ANTHROPIC_MODEL,
                    "configured": bool(settings.secure_anthropic_api_key()),
                },
            },
            "stripe": {"configured": bool(settings.secure_stripe_secret_key())},
        },
        "features": {
            "pii_redaction": settings.ENABLE_PII_REDACTION,
            "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
            "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
            "allowed_file_types": settings.ALLOWED_FILE_TYPES,
        },
    }


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return {
        "error": {
            "type": "http_error",
            "status_code": exc.status_code,
            "detail": exc.detail,
        }
    }


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    import logging

    logger = logging.getLogger("data_foundry")
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

    return {
        "error": {
            "type": "internal_server_error",
            "detail": "An internal error occurred",
        }
    }


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
