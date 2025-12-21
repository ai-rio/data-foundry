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

    async def close(self):
        """Close the audit service."""
        if self.audit_logger:
            await self.audit_logger.close()
            logger.info("AuditService closed")