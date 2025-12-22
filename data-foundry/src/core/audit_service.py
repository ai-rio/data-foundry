"""
Audit Service for Data Foundry

Provides audit logging functionality using the AuditLogger.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from src.core.audit import AuditLogger, AuditContext, AuditEventType

logger = logging.getLogger(__name__)


class AuditService:
    """
    Audit service that provides high-level audit logging functionality.
    """

    def __init__(self, enable_audit: bool = True):
        self.enable_audit = enable_audit
        self.audit_logger = None

        if enable_audit:
            try:
                self.audit_logger = AuditLogger()
                logger.info("AuditService initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize AuditLogger: {e}")
                self.audit_logger = None

    async def create_audit_log(
        self,
        tenant_id: str,
        operation: str,
        model: str,
        success: bool = True,
        cost: Optional[float] = None,
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        """
        Create an audit log entry.

        Args:
            tenant_id: Tenant identifier
            operation: Operation performed
            model: Model used
            success: Whether operation succeeded
            cost: Cost of operation
            usage: Token usage
            metadata: Additional metadata
            error_message: Error message if operation failed
        """
        if not self.audit_logger or not self.enable_audit:
            return

        try:
            # Create audit context
            context = AuditContext(
                request_id=f"req_{int(datetime.utcnow().timestamp())}",
                timestamp=datetime.utcnow()
            )

            # Prepare audit data
            audit_data = {
                "operation": operation,
                "model": model,
                "success": success,
                "metadata": metadata or {}
            }

            if cost is not None:
                audit_data["cost"] = cost

            if usage is not None:
                audit_data["usage"] = usage

            if error_message:
                audit_data["error_message"] = error_message

            # Log based on success/failure
            if success:
                # Log as cost calculation for successful operations
                await self.audit_logger.log_cost_calculation(
                    calculation_data=audit_data,
                    tenant_id=tenant_id,
                    context=context
                )
            else:
                # Log as system error for failures
                from src.core.audit import ImmutableAuditRecord
                import sys
                error = Exception(error_message or "Unknown error")

                await self.audit_logger.log_error(
                    error=error,
                    context=context,
                    tenant_id=tenant_id
                )

        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")

    async def log_ai_completion(
        self,
        tenant_id: str,
        prompt: str,
        response_content: str,
        model: str,
        cost: float,
        usage: Dict[str, int],
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log AI completion events.
        """
        await self.create_audit_log(
            tenant_id=tenant_id,
            operation="ai_completion",
            model=model,
            success=success,
            cost=cost,
            usage=usage,
            metadata={
                "prompt_length": len(prompt),
                "response_length": len(response_content),
                **(metadata or {})
            },
            error_message=error_message
        )

    async def log_consent_granted(
        self,
        user_id: str,
        consent_type: str,
        timestamp: datetime,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log consent granted event.

        Args:
            user_id: User identifier who granted consent
            consent_type: Type of consent granted
            timestamp: When consent was granted
            metadata: Additional context metadata (IP, user agent, consent text, etc.)
        """
        if not self.audit_logger or not self.enable_audit:
            return

        try:
            # Create audit context with user information
            context = AuditContext(
                request_id=f"consent_{int(datetime.utcnow().timestamp())}",
                user_id=user_id,
                ip_address=metadata.get("ip_address") if metadata else None,
                user_agent=metadata.get("user_agent") if metadata else None,
                timestamp=timestamp
            )

            # Prepare consent audit data
            consent_data = {
                "consent_type": consent_type,
                "consent_action": "granted",
                "consent_timestamp": timestamp.isoformat(),
                "gdpr_compliance": True,
                "metadata": metadata or {}
            }

            # Include GDPR-relevant fields
            if metadata:
                if "consent_text" in metadata:
                    # Include summary of consent text (not full text for privacy)
                    consent_text = metadata["consent_text"]
                    consent_data["consent_text_summary"] = (
                        consent_text[:100] + "..." if len(consent_text) > 100 else consent_text
                    )

                if "consent_purpose" in metadata:
                    consent_data["consent_purpose"] = metadata["consent_purpose"]

                if "data_retention_period" in metadata:
                    consent_data["data_retention_period"] = metadata["data_retention_period"]

            # Create immutable audit record
            from src.core.audit import ImmutableAuditRecord, AuditEventType
            record = ImmutableAuditRecord(
                event_type=AuditEventType.CONSENT_GRANTED,
                tenant_id=user_id,  # Use user_id as tenant for consent events
                calculation_id=f"consent_{consent_type}_{int(timestamp.timestamp())}",
                immutable_data=consent_data,
                context=context,
                timestamp=timestamp
            )

            # Log the consent event
            await self.audit_logger.log_event(record)
            logger.info(f"Logged consent granted for user {user_id}, type {consent_type}")

        except Exception as e:
            logger.error(f"Failed to log consent granted event: {e}")

    async def log_consent_withdrawn(
        self,
        user_id: str,
        consent_type: str,
        timestamp: datetime,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log consent withdrawn event.

        Args:
            user_id: User identifier who withdrew consent
            consent_type: Type of consent withdrawn
            timestamp: When consent was withdrawn
            metadata: Additional context metadata
        """
        if not self.audit_logger or not self.enable_audit:
            return

        try:
            # Create audit context with user information
            context = AuditContext(
                request_id=f"withdrawal_{int(datetime.utcnow().timestamp())}",
                user_id=user_id,
                ip_address=metadata.get("ip_address") if metadata else None,
                user_agent=metadata.get("user_agent") if metadata else None,
                timestamp=timestamp
            )

            # Prepare consent withdrawal audit data
            consent_data = {
                "consent_type": consent_type,
                "consent_action": "withdrawn",
                "consent_timestamp": timestamp.isoformat(),
                "gdpr_compliance": True,
                "gdpr_article": "7_3",  # Right to withdraw consent
                "metadata": metadata or {}
            }

            # Include GDPR-relevant fields
            if metadata:
                if "withdrawal_reason" in metadata:
                    consent_data["withdrawal_reason"] = metadata["withdrawal_reason"]

                if "immediate_effect" in metadata:
                    consent_data["immediate_effect"] = metadata["immediate_effect"]

            # Create immutable audit record
            from src.core.audit import ImmutableAuditRecord, AuditEventType
            record = ImmutableAuditRecord(
                event_type=AuditEventType.CONSENT_WITHDRAWN,
                tenant_id=user_id,  # Use user_id as tenant for consent events
                calculation_id=f"withdrawal_{consent_type}_{int(timestamp.timestamp())}",
                immutable_data=consent_data,
                context=context,
                timestamp=timestamp
            )

            # Log the consent withdrawal event
            await self.audit_logger.log_event(record)
            logger.info(f"Logged consent withdrawn for user {user_id}, type {consent_type}")

        except Exception as e:
            logger.error(f"Failed to log consent withdrawn event: {e}")

    async def log_consent_verified(
        self,
        user_id: str,
        consent_type: str,
        timestamp: datetime,
        verification_result: bool,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log consent verification event.

        Args:
            user_id: User identifier whose consent was verified
            consent_type: Type of consent verified
            timestamp: When verification occurred
            verification_result: True if consent is active, False if not
            metadata: Additional context metadata
        """
        if not self.audit_logger or not self.enable_audit:
            return

        try:
            # Create audit context
            context = AuditContext(
                request_id=f"verification_{int(datetime.utcnow().timestamp())}",
                user_id=user_id,
                timestamp=timestamp
            )

            # Prepare consent verification audit data
            consent_data = {
                "consent_type": consent_type,
                "consent_action": "verified",
                "verification_result": verification_result,
                "verification_timestamp": timestamp.isoformat(),
                "gdpr_compliance": True,
                "metadata": metadata or {}
            }

            # Include verification context
            if metadata:
                if "verification_purpose" in metadata:
                    consent_data["verification_purpose"] = metadata["verification_purpose"]

                if "system_component" in metadata:
                    consent_data["system_component"] = metadata["system_component"]

            # Create immutable audit record
            from src.core.audit import ImmutableAuditRecord, AuditEventType
            record = ImmutableAuditRecord(
                event_type=AuditEventType.CONSENT_VERIFIED,
                tenant_id=user_id,  # Use user_id as tenant for consent events
                calculation_id=f"verification_{consent_type}_{int(timestamp.timestamp())}",
                immutable_data=consent_data,
                context=context,
                timestamp=timestamp
            )

            # Log the consent verification event
            await self.audit_logger.log_event(record)
            logger.info(f"Logged consent verification for user {user_id}, type {consent_type}, result {verification_result}")

        except Exception as e:
            logger.error(f"Failed to log consent verification event: {e}")

    async def log_consent_objection(
        self,
        user_id: str,
        consent_type: str,
        timestamp: datetime,
        objection_reason: str,
        objection_category: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log consent objection event (GDPR Article 21).

        Args:
            user_id: User identifier who filed objection
            consent_type: Type of processing being objected to
            timestamp: When objection was filed
            objection_reason: Reason for objection
            objection_category: Category of objection (marketing, analytics, etc.)
            metadata: Additional context metadata
        """
        if not self.audit_logger or not self.enable_audit:
            return

        try:
            # Create audit context with user information
            context = AuditContext(
                request_id=f"objection_{int(datetime.utcnow().timestamp())}",
                user_id=user_id,
                ip_address=metadata.get("ip_address") if metadata else None,
                user_agent=metadata.get("user_agent") if metadata else None,
                timestamp=timestamp
            )

            # Prepare consent objection audit data
            consent_data = {
                "consent_type": consent_type,
                "consent_action": "objection",
                "objection_timestamp": timestamp.isoformat(),
                "objection_reason": objection_reason,
                "objection_category": objection_category,
                "gdpr_compliance": True,
                "gdpr_article": "21",  # Right to object to processing
                "legal_basis": "GDPR_Article_21",
                "metadata": metadata or {}
            }

            # Include objection context
            if metadata:
                if "processing_details" in metadata:
                    consent_data["processing_details"] = metadata["processing_details"]

                if "objection_scope" in metadata:
                    consent_data["objection_scope"] = metadata["objection_scope"]

            # Create immutable audit record
            from src.core.audit import ImmutableAuditRecord, AuditEventType
            record = ImmutableAuditRecord(
                event_type=AuditEventType.CONSENT_OBJECTION,
                tenant_id=user_id,  # Use user_id as tenant for consent events
                calculation_id=f"objection_{consent_type}_{int(timestamp.timestamp())}",
                immutable_data=consent_data,
                context=context,
                timestamp=timestamp
            )

            # Log the consent objection event
            await self.audit_logger.log_event(record)
            logger.info(f"Logged consent objection for user {user_id}, type {consent_type}, category {objection_category}")

        except Exception as e:
            logger.error(f"Failed to log consent objection event: {e}")

    async def close(self):
        """Close the audit service."""
        if self.audit_logger:
            await self.audit_logger.close()
            logger.info("AuditService closed")