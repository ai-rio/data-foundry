"""
Main FastAPI application for Data Foundry
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from src.core.config import settings
from src.app.middleware import (
    TenantContextMiddleware,
    SecurityHeadersMiddleware,
    RequestLoggingMiddleware
)
from src.core.security import get_current_user_token
from src.tasks.ingestion import data_ingestion_flow


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("🚀 Data Foundry is starting up...")
    print(f"📊 API Documentation: http://localhost:8000/docs")
    print(f"🏷️  Label Studio: http://localhost:8080")
    print(f"🔧 Prefect Dashboard: http://localhost:4200")

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
    lifespan=lifespan
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


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
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
        "health": "/health"
    }


# Protected endpoint example
@app.get("/api/v1/me")
async def get_current_user(current_user: dict = Depends(get_current_user_token)):
    """Get current user information."""
    return {
        "user_id": current_user.get("user_id"),
        "tenant_id": current_user.get("tenant_id"),
        "token_type": "bearer"
    }


# Trigger ingestion flow
@app.post("/api/v1/ingest")
async def trigger_ingestion(
    data_source: str = "sample_data",
    enable_ai: bool = True,
    enable_pii: bool = True,
    enable_human_review: bool = True,
    current_user: dict = Depends(get_current_user_token)
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
            enable_human_review=enable_human_review
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
                "enable_human_review": enable_human_review
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start ingestion flow: {str(e)}"
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
            "debug": settings.DEBUG
        },
        "services": {
            "database": {
                "url": settings.DATABASE_URL.split("@")[1] if "@" in settings.DATABASE_URL else "configured",
                "pool_size": settings.DATABASE_POOL_SIZE
            },
            "redis": {
                "url": settings.REDIS_URL.split("@")[1] if "@" in settings.REDIS_URL else "configured"
            },
            "label_studio": {
                "url": settings.LABEL_STUDIO_URL
            },
            "ai_providers": {
                "openai": {
                    "model": settings.OPENAI_MODEL,
                    "configured": bool(settings.OPENAI_API_KEY)
                },
                "anthropic": {
                    "model": settings.ANTHROPIC_MODEL,
                    "configured": bool(settings.ANTHROPIC_API_KEY)
                }
            },
            "stripe": {
                "configured": bool(settings.STRIPE_SECRET_KEY)
            }
        },
        "features": {
            "pii_redaction": settings.ENABLE_PII_REDACTION,
            "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
            "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
            "allowed_file_types": settings.ALLOWED_FILE_TYPES
        }
    }


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return {
        "error": {
            "type": "http_error",
            "status_code": exc.status_code,
            "detail": exc.detail
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
            "detail": "An internal error occurred"
        }
    }


if __name__ == "__main__":
    # Run the application
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )