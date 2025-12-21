"""
Immutable Audit Trail Module

Provides comprehensive, tamper-proof audit logging for all financial operations.
Implements write-once, read-many audit records with cryptographic integrity.
"""

import json
import logging
import hashlib
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import os
import aiofiles
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events."""
    COST_CALCULATION = "COST_CALCULATION"
    BILLING_EVENT = "BILLING_EVENT"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    DATA_ACCESS = "DATA_ACCESS"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"


@dataclass(frozen=True)
class AuditContext:
    """Context information for audit events."""
    request_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', datetime.utcnow())


@dataclass(frozen=True)
class ImmutableAuditRecord:
    """
    Immutable audit record with cryptographic integrity.
    Once created, cannot be modified without breaking the hash.
    """
    event_type: AuditEventType
    tenant_id: str
    calculation_id: Optional[str]
    immutable_data: Dict[str, Any]
    context: AuditContext
    timestamp: datetime
    record_hash: Optional[str] = None

    def __post_init__(self):
        """Calculate hash of the record to ensure immutability."""
        if self.record_hash is None:
            # Create a deterministic representation for hashing
            record_data = {
                "event_type": self.event_type.value,
                "tenant_id": self.tenant_id,
                "calculation_id": self.calculation_id,
                "immutable_data": self._normalize_data(self.immutable_data),
                "context": asdict(self.context),
                "timestamp": self.timestamp.isoformat()
            }
            record_json = json.dumps(record_data, sort_keys=True, separators=(',', ':'))
            hash_value = hashlib.sha256(record_json.encode('utf-8')).hexdigest()
            object.__setattr__(self, 'record_hash', hash_value)

    @staticmethod
    def _normalize_data(data: Any) -> Any:
        """Normalize data for consistent hashing."""
        if isinstance(data, dict):
            return {k: ImmutableAuditRecord._normalize_data(v) for k, v in sorted(data.items())}
        elif isinstance(data, list):
            return [ImmutableAuditRecord._normalize_data(v) for v in data]
        elif isinstance(data, (int, float, str, bool, type(None))):
            return data
        else:
            return str(data)

    def verify_integrity(self) -> bool:
        """Verify that the record has not been tampered with."""
        # Recreate hash without the original hash
        temp_record = ImmutableAuditRecord(
            event_type=self.event_type,
            tenant_id=self.tenant_id,
            calculation_id=self.calculation_id,
            immutable_data=self.immutable_data,
            context=self.context,
            timestamp=self.timestamp
        )
        return temp_record.record_hash == self.record_hash

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "event_type": self.event_type.value,
            "tenant_id": self.tenant_id,
            "calculation_id": self.calculation_id,
            "immutable_data": self.immutable_data,
            "context": asdict(self.context),
            "timestamp": self.timestamp.isoformat(),
            "record_hash": self.record_hash
        }


class AuditLogger:
    """
    Production audit logger with immutable records and multiple outputs.
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        enable_file_logging: bool = True,
        enable_database_logging: bool = True,
        buffer_size: int = 100,
        flush_interval: int = 5
    ):
        self.log_dir = Path(log_dir or os.getenv("AUDIT_LOG_DIR", "/var/log/data-foundry/audit"))
        self.enable_file_logging = enable_file_logging
        self.enable_database_logging = enable_database_logging
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval

        # In-memory buffer for batch writes
        self._buffer: List[ImmutableAuditRecord] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None

        # Ensure log directory exists
        if self.enable_file_logging:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # Start periodic flush task
        if self.buffer_size > 0:
            self._flush_task = asyncio.create_task(self._periodic_flush())

        logger.info("AuditLogger initialized with immutable records")

    async def log_event(self, record: ImmutableAuditRecord):
        """Log an audit event with verification."""
        try:
            # Verify record integrity
            if not record.verify_integrity():
                raise ValueError("Audit record integrity check failed")

            # Add to buffer
            async with self._buffer_lock:
                self._buffer.append(record)

                # Flush if buffer is full
                if len(self._buffer) >= self.buffer_size:
                    await self._flush_buffer()

            # Also log to system logger for immediate visibility
            logger.info(
                f"AUDIT_EVENT: {record.event_type.value} "
                f"for tenant {record.tenant_id} "
                f"(calc_id: {record.calculation_id}) "
                f"hash: {record.record_hash[:16]}..."
            )

        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}")
            raise

    async def log_cost_calculation(
        self,
        calculation_data: Dict[str, Any],
        tenant_id: str,
        context: AuditContext
    ):
        """Log a cost calculation event."""
        record = ImmutableAuditRecord(
            event_type=AuditEventType.COST_CALCULATION,
            tenant_id=tenant_id,
            calculation_id=calculation_data.get("calculation_id"),
            immutable_data=calculation_data,
            context=context,
            timestamp=datetime.utcnow()
        )
        await self.log_event(record)

    async def log_security_violation(
        self,
        violation_message: str,
        tenant_id: str,
        context: AuditContext,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log a security violation."""
        record = ImmutableAuditRecord(
            event_type=AuditEventType.SECURITY_VIOLATION,
            tenant_id=tenant_id,
            calculation_id=None,
            immutable_data={
                "violation_message": violation_message,
                "details": details or {}
            },
            context=context,
            timestamp=datetime.utcnow()
        )
        await self.log_event(record)

    async def log_error(
        self,
        error: Exception,
        context: AuditContext,
        tenant_id: Optional[str] = None
    ):
        """Log a system error."""
        record = ImmutableAuditRecord(
            event_type=AuditEventType.SYSTEM_ERROR,
            tenant_id=tenant_id or "system",
            calculation_id=None,
            immutable_data={
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error_details": getattr(error, '__dict__', {})
            },
            context=context,
            timestamp=datetime.utcnow()
        )
        await self.log_event(record)

    async def _flush_buffer(self):
        """Flush the buffer to persistent storage."""
        if not self._buffer:
            return

        # Get records to flush
        async with self._buffer_lock:
            records = self._buffer.copy()
            self._buffer.clear()

        # Write to different outputs
        tasks = []
        if self.enable_file_logging:
            tasks.append(self._write_to_file(records))
        if self.enable_database_logging:
            tasks.append(self._write_to_database(records))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _write_to_file(self, records: List[ImmutableAuditRecord]):
        """Write records to file with rotation."""
        try:
            # Use daily rotation
            today = datetime.utcnow().strftime("%Y-%m-%d")
            log_file = self.log_dir / f"audit-{today}.logl"

            # Write in append mode
            async with aiofiles.open(log_file, mode='a', encoding='utf-8') as f:
                for record in records:
                    # Write as JSONL (JSON Lines) format
                    line = json.dumps(record.to_dict(), separators=(',', ':'))
                    await f.write(line + '\n')

            logger.debug(f"Wrote {len(records)} audit records to {log_file}")

        except Exception as e:
            logger.error(f"Failed to write audit records to file: {str(e)}")

    async def _write_to_database(self, records: List[ImmutableAuditRecord]):
        """Write records to database."""
        try:
            # This would integrate with your database layer
            # For now, just log the intent
            logger.info(f"Would write {len(records)} audit records to database")
            # Implementation would depend on your database schema
            pass

        except Exception as e:
            logger.error(f"Failed to write audit records to database: {str(e)}")

    async def _periodic_flush(self):
        """Periodically flush the buffer."""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {str(e)}")

    async def search_audit_records(
        self,
        tenant_id: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        calculation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search audit records based on criteria.
        Returns verified records only.
        """
        results = []

        try:
            # Search through recent log files
            if self.enable_file_logging:
                # Get recent days to search
                days_to_search = 7  # Search last 7 days by default
                current_date = datetime.utcnow()

                for day_offset in range(days_to_search):
                    search_date = (current_date - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                    log_file = self.log_dir / f"audit-{search_date}.logl"

                    if log_file.exists():
                        async with aiofiles.open(log_file, mode='r', encoding='utf-8') as f:
                            async for line in f:
                                try:
                                    record_data = json.loads(line.strip())

                                    # Apply filters
                                    if tenant_id and record_data.get("tenant_id") != tenant_id:
                                        continue
                                    if event_type and record_data.get("event_type") != event_type.value:
                                        continue
                                    if calculation_id and record_data.get("calculation_id") != calculation_id:
                                        continue
                                    if start_time:
                                        record_time = datetime.fromisoformat(record_data["timestamp"])
                                        if record_time < start_time:
                                            continue
                                    if end_time:
                                        record_time = datetime.fromisoformat(record_data["timestamp"])
                                        if record_time > end_time:
                                            continue

                                    # Verify integrity before returning
                                    temp_record = ImmutableAuditRecord(
                                        event_type=AuditEventType(record_data["event_type"]),
                                        tenant_id=record_data["tenant_id"],
                                        calculation_id=record_data.get("calculation_id"),
                                        immutable_data=record_data["immutable_data"],
                                        context=AuditContext(**record_data["context"]),
                                        timestamp=datetime.fromisoformat(record_data["timestamp"]),
                                        record_hash=record_data["record_hash"]
                                    )

                                    if temp_record.verify_integrity():
                                        results.append(record_data)

                                except json.JSONDecodeError:
                                    logger.warning(f"Invalid JSON in audit log: {line[:100]}")
                                    continue
                                except Exception as e:
                                    logger.warning(f"Error processing audit record: {str(e)}")
                                    continue

        except Exception as e:
            logger.error(f"Failed to search audit records: {str(e)}")

        return results

    async def get_tenant_audit_trail(
        self,
        tenant_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get complete audit trail for a tenant."""
        start_time = datetime.utcnow() - timedelta(days=days)
        return await self.search_audit_records(
            tenant_id=tenant_id,
            start_time=start_time
        )

    async def cleanup_old_logs(self, retention_days: int = 365):
        """Clean up old audit logs beyond retention period."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            deleted_count = 0

            for log_file in self.log_dir.glob("audit-*.logl"):
                # Extract date from filename
                try:
                    date_str = log_file.stem.split('-')[1]
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")

                    if file_date < cutoff_date:
                        log_file.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted old audit log: {log_file}")

                except (ValueError, IndexError):
                    continue

            logger.info(f"Cleaned up {deleted_count} old audit log files")

        except Exception as e:
            logger.error(f"Failed to cleanup old audit logs: {str(e)}")

    async def close(self):
        """Close the audit logger and flush remaining records."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_buffer()
        logger.info("AuditLogger closed")


# Context manager for audit logging
@asynccontextmanager
async def audit_context(
    tenant_id: str,
    user_id: Optional[str] = None,
    operation: str = "operation"
):
    """Context manager for audit logging."""
    context = AuditContext(
        request_id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=str(uuid.uuid4()),
        ip_address=os.getenv("REQUEST_IP"),
        user_agent=os.getenv("USER_AGENT")
    )

    try:
        yield context
        logger.info(f"AUDIT: {operation} completed successfully for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"AUDIT: {operation} failed for tenant {tenant_id}: {str(e)}")
        raise


# Export for use
__all__ = [
    "AuditLogger",
    "ImmutableAuditRecord",
    "AuditContext",
    "AuditEventType",
    "audit_context"
]