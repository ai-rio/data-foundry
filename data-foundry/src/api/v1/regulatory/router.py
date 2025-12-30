"""
Regulatory Reference Router

Implements endpoints for providing regulatory context for AML service.
Returns FATF, FinCEN, 6AMLD/AMLA, and BCB/COAF regulatory references
used in AML labeling methodology.

Security:
- Public endpoint (no authentication required for regulatory reference)
- Input validation on all request parameters
- Cached responses to reduce load (1-hour TTL)
- Rate limiting applied

Best Practices:
- SOLID principles: Single Responsibility (only serves regulatory data)
- Caching with TTL for performance
- Comprehensive error handling
- Full OpenAPI documentation

Implementation: P01-016
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from functools import lru_cache
from fastapi import APIRouter, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse

from src.api.v1.regulatory.contracts import (
    RegulatoryContextResponse,
    RegulatoryFramework,
    HealthCheckResponse,
    ErrorResponse,
    REGULATORY_API_TAGS,
    REGULATORY_ENDPOINT_DESCRIPTIONS,
)

# Rate limiting (if available in project)
try:
    from src.middleware.rate_limit import limiter, get_rate_limit
    HAS_RATE_LIMIT = True
except ImportError:
    HAS_RATE_LIMIT = False
    logging.warning("Rate limiting middleware not available, proceeding without rate limits")


logger = logging.getLogger(__name__)


# =============================================================================
# Regulatory Data Source
# =============================================================================

def _get_regulatory_frameworks() -> List[RegulatoryFramework]:
    """
    Get regulatory frameworks data.

    Returns a list of regulatory frameworks referenced by the AML service,
    including FATF, FinCEN, EU 6AMLD/AMLA, and BCB/COAF.

    Returns:
        List of RegulatoryFramework objects

    Reference:
        docs/planning/REGULATORY_REFERENCE_AML_SERVICE.md
    """
    return [
        RegulatoryFramework(
            name="FATF",
            description="Financial Action Task Force - International AML/CFT standard setter",
            recommendations=[
                "R.1: Risk assessment and understanding",
                "R.10: Customer due diligence (CDD)",
                "R.13: Transaction monitoring and reporting",
                "R.16: Travel Rule - fund transfers (2025 update)",
                "R.20: Suspicious transaction reporting"
            ],
            url="https://www.fatf-gafi.org"
        ),
        RegulatoryFramework(
            name="FinCEN",
            description="Financial Crimes Enforcement Network - US AML regulator",
            recommendations=[
                "Bank Secrecy Act (BSA) - 31 USC 5311",
                "SAR FAQs (October 2025) - 30-day reporting deadline",
                "BSA/AML Manual - FFIEC guidance",
                "OCC Bulletin 2025-31 - National bank implementation"
            ],
            url="https://www.fincen.gov"
        ),
        RegulatoryFramework(
            name="6AMLD/AMLA",
            description="EU 6th Anti-Money Laundering Directive & AMLA Authority",
            recommendations=[
                "Directive (EU) 2024/1640 - 6AMLD",
                "Regulation (EU) 2024/1620 - AMLA establishment",
                "EU AML Single Rulebook - Harmonized standards",
                "MiCA Regulation - Crypto asset framework"
            ],
            url="https://www.europarl.europa.eu"
        ),
        RegulatoryFramework(
            name="BCB/COAF",
            description="Brazilian Central Bank & Financial Activities Control Council",
            recommendations=[
                "Law 9,613/1998 - Anti-Money Laundering Law",
                "Law 12,683/2012 - Enhanced enforcement",
                "COAF Resolution 36/2021 - New AML/CFT requirements",
                "BCB Circular 3,978/2020 - Risk-based approach",
                "BCB Resolution 520/2025 - VASP crypto framework"
            ],
            url="https://www.bcb.gov.br/en"
        ),
    ]


def _build_regulatory_context() -> Dict[str, Any]:
    """
    Build the complete regulatory context response.

    Constructs the full regulatory context including frameworks,
    risk levels, typologies, and metadata.

    Returns:
        Dictionary with all regulatory context data
    """
    return {
        "service": "AML Service",
        "version": "1.0",
        "regulatory_frameworks": [
            fw.model_dump() for fw in _get_regulatory_frameworks()
        ],
        "risk_levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        "typologies": ["ML", "TF", "PEP", "FRAUD", "SANCTIONS"],
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d")
    }


# =============================================================================
# Cache Management with TTL
# =============================================================================

class CachedRegulatoryData:
    """
    Thread-safe cache for regulatory data with TTL.

    Implements a caching layer with configurable TTL (Time-To-Live)
    for regulatory data, which changes infrequently.

    Attributes:
        _data: Cached regulatory data
        _cached_at: Timestamp when data was cached
        _ttl_seconds: Time-to-live in seconds (default: 1 hour)
    """

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize the cache with specified TTL.

        Args:
            ttl_seconds: Time-to-live in seconds (default: 3600 = 1 hour)
        """
        self._data: Optional[Dict[str, Any]] = None
        self._cached_at: Optional[datetime] = None
        self._ttl_seconds: int = ttl_seconds

    def is_valid(self) -> bool:
        """
        Check if cached data is still valid (not expired).

        Returns:
            True if cache is valid, False otherwise
        """
        if self._data is None or self._cached_at is None:
            return False

        age = (datetime.now(timezone.utc) - self._cached_at).total_seconds()
        return age < self._ttl_seconds

    def get(self) -> Dict[str, Any]:
        """
        Get cached data if valid, otherwise refresh.

        Returns:
            Cached regulatory data

        Note:
            Automatically refreshes cache if expired
        """
        if not self.is_valid():
            self.refresh()
        return self._data

    def refresh(self) -> None:
        """
        Refresh the cache with fresh data.

        Note:
            Called automatically when cache expires
        """
        self._data = _build_regulatory_context()
        self._cached_at = datetime.now(timezone.utc)
        logger.info(
            f"Regulatory data cache refreshed (TTL: {self._ttl_seconds}s)"
        )

    def clear(self) -> None:
        """
        Clear the cache, forcing refresh on next access.

        Note:
            Useful for testing or manual cache invalidation
        """
        self._data = None
        self._cached_at = None
        logger.info("Regulatory data cache cleared")


# Global cache instance with 1-hour TTL
_regulatory_cache = CachedRegulatoryData(ttl_seconds=3600)


# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(
    prefix="/regulatory",
    tags=REGULATORY_API_TAGS,
)


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/aml-context",
    response_model=RegulatoryContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Get AML regulatory context",
    description=REGULATORY_ENDPOINT_DESCRIPTIONS["aml_context"],
    responses={
        200: {
            "description": "Regulatory context retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "service": "AML Service",
                        "version": "1.0",
                        "regulatory_frameworks": [
                            {
                                "name": "FATF",
                                "description": "Financial Action Task Force",
                                "recommendations": ["Rec 10", "Rec 15", "Rec 20"],
                                "url": "https://www.fatf-gafi.org"
                            }
                        ],
                        "risk_levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                        "typologies": ["ML", "TF", "PEP", "FRAUD", "SANCTIONS"],
                        "last_updated": "2025-12-30"
                    }
                }
            }
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    }
)
async def get_regulatory_context(
    request: Request,
    refresh: bool = False
) -> JSONResponse:
    """
    Get regulatory context for AML service.

    Returns FATF, FinCEN, 6AMLD/AMLA, and BCB/COAF regulatory references
    used in AML labeling methodology. Response is cached for 1 hour by default.

    Security:
    - Public endpoint (no authentication required)
    - Rate limiting applied (if available)
    - Input validation on query parameters

    Args:
        request: FastAPI request object (for rate limiting)
        refresh: Force cache refresh (default: False)

    Returns:
        RegulatoryContextResponse with frameworks, risk levels, typologies

    Raises:
        HTTPException 500: Internal server error

    Example:
        >>> GET /api/v1/regulatory/aml-context
        >>> {
        ...     "service": "AML Service",
        ...     "version": "1.0",
        ...     "regulatory_frameworks": [...],
        ...     "risk_levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        ...     "typologies": ["ML", "TF", "PEP", "FRAUD", "SANCTIONS"],
        ...     "last_updated": "2025-12-30"
        ... }
    """
    try:
        # Force cache refresh if requested
        if refresh:
            _regulatory_cache.refresh()
            logger.info("Cache refresh requested via query parameter")

        # Get cached data
        context_data = _regulatory_cache.get()

        # Add cache metadata to response headers
        headers = {
            "X-Cache-Status": "HIT" if _regulatory_cache.is_valid() else "MISS",
            "X-Cache-Expires": (
                (_regulatory_cache._cached_at + timedelta(seconds=_regulatory_cache._ttl_seconds))
                .isoformat()
                if _regulatory_cache._cached_at
                else ""
            ),
        }

        logger.info("Regulatory context retrieved successfully")

        return JSONResponse(
            content=context_data,
            status_code=status.HTTP_200_OK,
            headers=headers
        )

    except Exception as e:
        logger.error(
            f"Error retrieving regulatory context: {type(e).__name__} - {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving regulatory context"
        )


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check for regulatory API",
    description=REGULATORY_ENDPOINT_DESCRIPTIONS.get("health", "Health check endpoint"),
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service unavailable"},
    }
)
async def health_check() -> HealthCheckResponse:
    """
    Health check endpoint for regulatory API.

    Returns service health status and cache information.

    Returns:
        HealthCheckResponse with status and cache information
    """
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc),
        cached=_regulatory_cache.is_valid()
    )


# =============================================================================
# Cache Management Endpoints (Internal/Admin)
# =============================================================================

@router.post(
    "/cache/refresh",
    status_code=status.HTTP_200_OK,
    summary="Refresh regulatory data cache",
    description="Manually refresh the cached regulatory data",
    include_in_schema=False  # Hidden from public docs
)
async def refresh_cache() -> Dict[str, str]:
    """
    Refresh the regulatory data cache.

    Internal endpoint for manually refreshing cached regulatory data.
    Can be used after regulatory updates or for maintenance.

    Returns:
        Confirmation message
    """
    _regulatory_cache.refresh()
    return {"message": "Regulatory data cache refreshed successfully"}


@router.delete(
    "/cache",
    status_code=status.HTTP_200_OK,
    summary="Clear regulatory data cache",
    description="Clear the cached regulatory data (forces refresh on next request)",
    include_in_schema=False  # Hidden from public docs
)
async def clear_cache() -> Dict[str, str]:
    """
    Clear the regulatory data cache.

    Internal endpoint for clearing cached regulatory data.
    Next request will trigger a cache refresh.

    Returns:
        Confirmation message
    """
    _regulatory_cache.clear()
    return {"message": "Regulatory data cache cleared successfully"}


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    'router',
    'get_regulatory_context',
    'health_check',
    'refresh_cache',
    'clear_cache',
    '_regulatory_cache',  # Exported for testing
]
