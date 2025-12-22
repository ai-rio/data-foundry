"""
Consent API Router Implementation

Implements consent management endpoints following REST principles and OpenAPI standards.
This handles HTTP requests, validation, and response formatting for consent operations.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import JSONResponse

from src.api.v1.consent.contracts import (
    # Request models
    GrantConsentRequest,
    WithdrawConsentRequest,
    ObjectToProcessingRequest,
    VerifyConsentRequest,
    ConsentQueryParams,
    # Response models
    ConsentRecordResponse,
    ConsentHistoryResponse,
    ConsentVerificationResponse,
    ObjectionResponse,
    ErrorResponse,
    SuccessResponse,
    # Enumerations
    ConsentType,
    ConsentStatus,
    # Documentation
    CONSENT_API_TAGS,
    CONSENT_ENDPOINT_DESCRIPTIONS,
)
from src.core.consent_manager import ConsentManager
from src.core.database import DatabaseManager
from src.core.audit_service import AuditService
from src.core.security import get_current_user_token
from src.core.config import settings

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/consent",
    tags=CONSENT_API_TAGS,
    responses={404: {"model": ErrorResponse, "description": "Not found"}},
)

# Authorization helper
def verify_user_access(current_user: dict, target_user_id: str) -> None:
    """
    Verify that the current user can access the target user's consent data.

    Args:
        current_user: Current authenticated user from JWT token
        target_user_id: User ID being accessed

    Raises:
        HTTPException: If user is not authorized
    """
    # Users can only access their own consent data
    if current_user.get("user_id") != target_user_id:
        logger.warning(
            f"Unauthorized access attempt: user {current_user.get('user_id')} "
            f"trying to access consent data for user {target_user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own consent data"
        )

# Dependencies
async def get_consent_manager() -> ConsentManager:
    """Dependency injection for consent manager."""
    # Initialize database manager
    db_manager = DatabaseManager()
    await db_manager.initialize()

    # Initialize audit service
    audit_service = AuditService()

    # Create and return consent manager
    return ConsentManager(db_manager, audit_service)


# Rate limiting middleware (simplified implementation)
class ConsentRateLimiter:
    """Simple in-memory rate limiter for consent endpoints."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[datetime]] = {}

    async def check_rate_limit(self, user_id: str, endpoint: str) -> bool:
        """Check if user has exceeded rate limit."""
        key = f"{user_id}:{endpoint}"
        now = datetime.now(timezone.utc)

        # Clean old requests
        if key in self.requests:
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if (now - req_time).total_seconds() < self.window_seconds
            ]
        else:
            self.requests[key] = []

        # Check if under limit
        if len(self.requests[key]) < self.max_requests:
            self.requests[key].append(now)
            return True

        return False


# Initialize rate limiter
rate_limiter = ConsentRateLimiter()


# Error handling utility
def handle_consent_error(func):
    """Decorator for consistent error handling in consent endpoints."""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error in {func.__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except PermissionError as e:
            logger.error(f"Permission error in {func.__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
    return wrapper


# Endpoints

@router.post(
    "/grant",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant new consent",
    description=CONSENT_ENDPOINT_DESCRIPTIONS["grant"],
    responses={
        201: {"description": "Consent granted successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def grant_consent(
    request: GrantConsentRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Grant new consent for data processing.

    Records a new consent according to GDPR Article 7 requirements.
    """
    # Rate limiting check
    user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(user_id, "grant_consent"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Extract IP and user agent from request if not provided
    metadata = request.metadata.dict()
    metadata["ip"] = metadata.get("ip", http_request.client.host if http_request.client else "unknown")
    metadata["user_agent"] = metadata.get("user_agent", http_request.headers.get("user-agent", "unknown"))

    # Record consent
    consent_record = await consent_manager.record_consent(
        user_id=request.user_id,
        consent_type=request.consent_type.value,
        consent_text=request.consent_text,
        metadata=metadata
    )

    logger.info(f"Consent granted for user {request.user_id}, type {request.consent_type}")

    return SuccessResponse(
        message="Consent granted successfully",
        data={
            "consent_id": consent_record.id if hasattr(consent_record, 'id') else None,
            "user_id": consent_record.user_id,
            "consent_type": consent_record.consent_type,
            "granted_at": consent_record.granted_at.isoformat(),
            "status": consent_record.status.value
        }
    )


@router.post(
    "/withdraw",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Withdraw consent",
    description=CONSENT_ENDPOINT_DESCRIPTIONS["withdraw"],
    responses={
        200: {"description": "Consent withdrawn successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "Consent not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def withdraw_consent(
    request: WithdrawConsentRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Withdraw previously granted consent.

    Implements the right to withdraw consent under GDPR Article 7(3).
    """
    # Rate limiting check
    user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(user_id, "withdraw_consent"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Extract IP and user agent from request if not provided
    metadata = request.metadata.dict()
    metadata["ip"] = metadata.get("ip", http_request.client.host if http_request.client else "unknown")
    metadata["user_agent"] = metadata.get("user_agent", http_request.headers.get("user-agent", "unknown"))
    metadata["withdrawal_reason"] = request.reason

    # Withdraw consent
    success = await consent_manager.withdraw_consent(
        user_id=request.user_id,
        consent_type=request.consent_type.value
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active consent found for user {request.user_id} of type {request.consent_type}"
        )

    logger.info(f"Consent withdrawn for user {request.user_id}, type {request.consent_type}")

    return SuccessResponse(
        message="Consent withdrawn successfully",
        data={
            "user_id": request.user_id,
            "consent_type": request.consent_type.value,
            "withdrawn_at": datetime.now(timezone.utc).isoformat()
        }
    )


@router.get(
    "/verify/{user_id}/{consent_type}",
    response_model=ConsentVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify consent status",
    description=CONSENT_ENDPOINT_DESCRIPTIONS["verify"],
    responses={
        200: {"description": "Consent verification result"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def verify_consent(
    user_id: str,
    consent_type: ConsentType,
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Verify if a user has active consent for a specific type of processing.

    Useful for pre-processing checks and consent-gated features.
    """
    # Authorization check - users can only verify their own consent
    verify_user_access(current_user, user_id)

    # Rate limiting check
    current_user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(current_user_id, "verify_consent"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Verify consent
    has_consent = await consent_manager.verify_consent(
        user_id=user_id,
        consent_type=consent_type.value
    )

    # Get detailed consent information if available
    consent_record = None
    if has_consent:
        # Try to get the actual consent record for details
        try:
            consent_record = await consent_manager.db_manager.get_active_consent(
                user_id=user_id,
                consent_type=consent_type.value
            )
        except Exception:
            # If we can't get details, just return the boolean result
            pass

    response_data = {
        "user_id": user_id,
        "consent_type": consent_type.value,
        "has_consent": has_consent,
        "granted_at": consent_record.granted_at if consent_record else None,
        "status": consent_record.status if consent_record else None,
        "last_updated": (
            consent_record.withdrawn_at or consent_record.granted_at
            if consent_record else None
        )
    }

    return ConsentVerificationResponse(**response_data)


@router.post(
    "/object",
    response_model=ObjectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Object to processing",
    description=CONSENT_ENDPOINT_DESCRIPTIONS["object"],
    responses={
        201: {"description": "Objection recorded successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def object_to_processing(
    request: ObjectToProcessingRequest,
    http_request: Request,
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Object to processing of personal data (GDPR Article 21).

    Users can object to processing even without prior consent.
    """
    # Rate limiting check
    user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(user_id, "object_to_processing"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Extract IP and user agent from request if not provided
    metadata = request.metadata.dict()
    metadata["ip"] = metadata.get("ip", http_request.client.host if http_request.client else "unknown")
    metadata["user_agent"] = metadata.get("user_agent", http_request.headers.get("user-agent", "unknown"))

    # Record objection
    success = await consent_manager.object_to_processing(
        user_id=request.user_id,
        consent_type=request.consent_type.value,
        reason=request.reason,
        category=request.category.value
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record objection"
        )

    logger.info(f"Objection recorded for user {request.user_id}, type {request.consent_type}")

    # For now, create a simple response
    # In a full implementation, we'd return the actual objection record ID
    return ObjectionResponse(
        user_id=request.user_id,
        consent_type=request.consent_type.value,
        objection_id=0,  # Placeholder - would get actual ID from database
        category=request.category.value,
        created_at=datetime.now(timezone.utc),
        status="active"
    )


@router.get(
    "/user/{user_id}",
    response_model=List[ConsentRecordResponse],
    status_code=status.HTTP_200_OK,
    summary="Get user's current consents",
    description=CONSENT_ENDPOINT_DESCRIPTIONS["user_consents"],
    responses={
        200: {"description": "User consents retrieved successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "User not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def get_user_consents(
    user_id: str,
    consent_type: Optional[ConsentType] = Query(None, description="Filter by consent type"),
    status_filter: Optional[ConsentStatus] = Query(ConsentStatus.ACTIVE, description="Filter by status"),
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Get all current consents for a user.

    Returns a user's current consent status, useful for preference centers.
    """
    # Authorization check - users can only access their own consent data
    verify_user_access(current_user, user_id)
    # Rate limiting check
    current_user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(current_user_id, "get_user_consents"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Get user's consent history
    consent_history = await consent_manager.db_manager.get_consent_history(
        user_id=user_id,
        consent_type=consent_type.value if consent_type else None
    )

    # Filter by status if specified
    if status_filter:
        consent_history = [
            record for record in consent_history
            if record.get("status") == status_filter.value
        ]

    # Convert to response models
    response_consents = []
    for record in consent_history:
        consent_response = ConsentRecordResponse(
            id=record.get("id", 0),
            user_id=record.get("user_id", user_id),
            consent_type=record.get("consent_type", ""),
            consent_text=record.get("consent_text", ""),
            granted_at=record.get("granted_at", datetime.now(timezone.utc)),
            status=ConsentStatus(record.get("status", ConsentStatus.ACTIVE)),
            withdrawn_at=record.get("withdrawn_at"),
            metadata=record.get("metadata", {})
        )
        response_consents.append(consent_response)

    return response_consents


@router.delete(
    "/user/{user_id}",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete user consent data (GDPR Article 17)",
    description="Permanently delete all consent data for a user (Right to Erasure)",
    responses={
        200: {"description": "Consent data deleted successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "User not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def delete_consent_data(
    user_id: str,
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Delete all consent data for a user (GDPR Article 17 - Right to Erasure).

    This permanently removes all consent records and associated audit data.
    This action cannot be undone and should require explicit confirmation.
    """
    # Authorization check - users can only delete their own consent data
    verify_user_access(current_user, user_id)

    # Rate limiting check for deletion operation
    current_user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(current_user_id, "delete_consent"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Get database manager directly for bulk deletion
    db_manager = consent_manager.db_manager

    # Delete all consent records for the user
    deleted_records = await db_manager.delete_user_consent_data(user_id)

    logger.info(f"Consent data deletion completed for user {user_id}: {deleted_records} records deleted")

    return SuccessResponse(
        success=True,
        message=f"All consent data for user {user_id} has been permanently deleted ({deleted_records} records)",
        timestamp=datetime.now(timezone.utc),
        data={"deleted_records": deleted_records}
    )


@router.get(
    "/user/{user_id}/export",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Export user consent data (GDPR Article 20)",
    description="Export all consent data in machine-readable format (Right to Data Portability)",
    responses={
        200: {"description": "Consent data exported successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "User not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def export_consent_data(
    user_id: str,
    format: str = Query("json", pattern="^(json|csv)$", description="Export format: json or csv"),
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Export all consent data for a user (GDPR Article 20 - Right to Data Portability).

    Provides machine-readable export of all consent records and audit trail.
    """
    # Authorization check - users can only export their own consent data
    verify_user_access(current_user, user_id)

    # Rate limiting check for export operation
    current_user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(current_user_id, "export_consent"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Get complete consent history for the user
    consent_history = await consent_manager.db_manager.get_consent_history(user_id)

    # Convert to export format
    export_data = {
        "user_id": user_id,
        "export_date": datetime.now(timezone.utc).isoformat(),
        "total_records": len(consent_history),
        "consent_records": []
    }

    for record in consent_history:
        consent_record = {
            "consent_id": record.id,
            "consent_type": record.consent_type,
            "status": record.status,
            "consent_text": record.consent_text,
            "granted_at": record.granted_at.isoformat() if record.granted_at else None,
            "withdrawn_at": record.withdrawn_at.isoformat() if record.withdrawn_at else None,
            "ip_address": record.ip_address,
            "user_agent": record.user_agent,
            "metadata": record.consent_metadata,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None
        }
        export_data["consent_records"].append(consent_record)

    logger.info(f"Consent data export completed for user {user_id}: {len(consent_history)} records")

    if format == "csv":
        # For CSV, return content as text with appropriate headers
        from fastapi.responses import PlainTextResponse
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "consent_id", "user_id", "consent_type", "status", "consent_text",
            "granted_at", "withdrawn_at", "ip_address", "user_agent",
            "created_at", "updated_at"
        ])

        # Write data
        for record in export_data["consent_records"]:
            writer.writerow([
                record["consent_id"],
                user_id,
                record["consent_type"],
                record["status"],
                record["consent_text"],
                record["granted_at"],
                record["withdrawn_at"],
                record["ip_address"],
                record["user_agent"],
                record["created_at"],
                record["updated_at"]
            ])

        return PlainTextResponse(
            content=output.getvalue(),
            headers={
                "Content-Disposition": f"attachment; filename=consent_data_{user_id}.csv"
            }
        )
    else:
        # JSON format (default)
        return export_data


@router.get(
    "/user/{user_id}/history",
    response_model=ConsentHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get consent history",
    description=CONSENT_ENDPOINT_DESCRIPTIONS["history"],
    responses={
        200: {"description": "Consent history retrieved successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "User not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
@handle_consent_error
async def get_consent_history(
    user_id: str,
    consent_type: Optional[ConsentType] = Query(None, description="Filter by consent type"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    per_page: int = Query(20, ge=1, le=100, description="Records per page (max 100)"),
    current_user: dict = Depends(get_current_user_token),
    consent_manager: ConsentManager = Depends(get_consent_manager)
):
    """
    Retrieve the complete consent history for a user.

    Provides an audit trail of all consent activities for GDPR compliance.
    """
    # Authorization check - users can only access their own consent data
    verify_user_access(current_user, user_id)

    # Rate limiting check
    current_user_id = current_user.get("user_id", "anonymous")
    if not await rate_limiter.check_rate_limit(current_user_id, "get_consent_history"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )

    # Get user's consent history
    consent_history = await consent_manager.db_manager.get_consent_history(
        user_id=user_id,
        consent_type=consent_type.value if consent_type else None
    )

    # Pagination
    total_records = len(consent_history)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_records = consent_history[start_idx:end_idx]

    # Convert to response models
    response_records = []
    for record in page_records:
        consent_response = ConsentRecordResponse(
            id=record.get("id", 0),
            user_id=record.get("user_id", user_id),
            consent_type=record.get("consent_type", ""),
            consent_text=record.get("consent_text", ""),
            granted_at=record.get("granted_at", datetime.now(timezone.utc)),
            status=ConsentStatus(record.get("status", ConsentStatus.ACTIVE)),
            withdrawn_at=record.get("withdrawn_at"),
            metadata=record.get("metadata", {})
        )
        response_records.append(consent_response)

    return ConsentHistoryResponse(
        user_id=user_id,
        consent_type=consent_type.value if consent_type else None,
        records=response_records,
        total=total_records,
        page=page,
        per_page=per_page,
        has_more=end_idx < total_records
    )