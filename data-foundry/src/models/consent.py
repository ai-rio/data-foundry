"""
Consent Database Models for Data Foundry

This module defines the SQLModel for consent records, providing:
- GDPR-compliant consent storage
- Indexed queries for performance
- JSON metadata support
- Audit trail capabilities
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from pydantic import field_validator, ValidationError
from sqlalchemy import Column, String, DateTime, Text, JSON, Index
from sqlmodel import SQLModel, Field

from src.models.enums import ConsentStatus


class ConsentRecordDB(SQLModel, table=True):
    """
    Consent record database model for GDPR-compliant consent storage.

    Stores consent records with full audit trail and metadata support.
    Indexed for efficient queries on common patterns (user lookups, consent types).
    """

    __tablename__ = "consent_records"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Core consent fields (required)
    user_id: str = Field(index=True, description="User identifier who granted consent")
    consent_type: str = Field(index=True, description="Type of consent (e.g., data_processing, marketing)")
    consent_text: str = Field(sa_column=Column(Text), description="Full consent text as shown to user")
    granted_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="When consent was granted"
    )
    ip_address: str = Field(description="IP address of user when consent was granted")
    user_agent: str = Field(
        sa_column=Column(Text),
        description="Browser/client identifier of user when consent was granted"
    )

    # Consent lifecycle fields
    status: ConsentStatus = Field(default=ConsentStatus.ACTIVE, description="Current status of consent")
    withdrawn_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When consent was withdrawn (if applicable)"
    )

    # Metadata and audit fields
    consent_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional metadata about the consent (source, version, etc.)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="When this record was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="When this record was last updated"
    )

    # Table indexes for performance
    __table_args__ = (
        Index('idx_consent_user_type', 'user_id', 'consent_type'),
        Index('idx_consent_status', 'status'),
        Index('idx_consent_granted_at', 'granted_at'),
        Index('idx_consent_user_status', 'user_id', 'status'),
    )

    @field_validator('user_id', 'consent_type', 'consent_text', 'ip_address', 'user_agent')
    @classmethod
    def validate_required_fields(cls, v, info):
        """Validate that required fields are not empty"""
        field_name = info.field_name
        if v is None or (isinstance(v, str) and v.strip() == ""):
            raise ValueError(f"{field_name} cannot be empty")
        return v.strip() if isinstance(v, str) else v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Validate status is a valid consent status"""
        if v not in [s.value for s in ConsentStatus]:
            raise ValueError(f"Invalid status: {v}")
        return v

    def withdraw(self) -> None:
        """
        Withdraw consent by updating status and timestamp.

        GDPR Art 7(3): Right to withdraw consent at any time.
        """
        self.status = ConsentStatus.WITHDRAWN
        self.withdrawn_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def is_active(self) -> bool:
        """
        Check if consent is currently active.

        Returns:
            True if consent is active and not withdrawn
        """
        return self.status == ConsentStatus.ACTIVE

    def to_domain_model(self):
        """
        Convert to domain model dictionary.

        Returns:
            Dictionary with domain model data
        """
        return {
            "user_id": self.user_id,
            "consent_type": self.consent_type,
            "consent_text": self.consent_text,
            "granted_at": self.granted_at,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "status": self.status,
            "withdrawn_at": self.withdrawn_at,
            "metadata": self.consent_metadata
        }

    @classmethod
    def from_domain_model(cls, domain_record):
        """
        Create database model from domain model.

        Args:
            domain_record: ConsentRecord domain model or dictionary

        Returns:
            ConsentRecordDB instance
        """
        # Handle both domain objects and dictionaries
        if hasattr(domain_record, 'user_id'):
            # Domain object
            return cls(
                user_id=domain_record.user_id,
                consent_type=domain_record.consent_type,
                consent_text=domain_record.consent_text,
                granted_at=domain_record.granted_at,
                ip_address=domain_record.ip_address,
                user_agent=domain_record.user_agent,
                status=domain_record.status,
                withdrawn_at=domain_record.withdrawn_at,
                consent_metadata=domain_record.metadata
            )
        else:
            # Dictionary
            return cls(
                user_id=domain_record["user_id"],
                consent_type=domain_record["consent_type"],
                consent_text=domain_record["consent_text"],
                granted_at=domain_record["granted_at"],
                ip_address=domain_record["ip_address"],
                user_agent=domain_record["user_agent"],
                status=domain_record["status"],
                withdrawn_at=domain_record["withdrawn_at"],
                consent_metadata=domain_record["metadata"]
            )

    def __repr__(self) -> str:
        """String representation of consent record"""
        status = "active" if self.is_active() else "withdrawn"
        return f"ConsentRecordDB(id={self.id}, user_id='{self.user_id}', type='{self.consent_type}', status='{status}')"