"""
Consent Management System for Data Foundry

Implements GDPR-compliant consent management with audit trails.
Follows TDD principles - implementation driven by tests.

GDPR References:
- Article 7(1): Conditions for consent (specific, informed, unambiguous)
- Article 7(3): Right to withdraw consent + demonstrable consent
- Article 21: Right to object to processing
"""

import hashlib
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.models.enums import ConsentStatus


def hash_ip_address(ip_address: str, salt: str = None) -> str:
    """
    Hash IP address for privacy protection (GDPR compliance).

    Args:
        ip_address: Raw IP address
        salt: Optional salt for hashing (uses environment variable if not provided)

    Returns:
        Hashed IP address
    """
    if salt is None:
        salt = os.getenv("IP_HASH_SALT", "default-salt-change-in-production")

    return hashlib.sha256(f"{ip_address}{salt}".encode()).hexdigest()


class ConsentRecord:
    """
    Consent record data model.

    Immutable record of consent granted by a user, compliant with GDPR requirements.
    """

    def __init__(
        self,
        user_id: str,
        consent_type: str,
        consent_text: str,
        granted_at: datetime,
        ip_address: str,
        user_agent: str,
        status: ConsentStatus = ConsentStatus.ACTIVE,
        withdrawn_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        # Validate required fields
        if not user_id or not user_id.strip():
            raise ValueError("User ID cannot be empty")
        if not consent_type or not consent_type.strip():
            raise ValueError("Consent type cannot be empty")
        if not consent_text or not consent_text.strip():
            raise ValueError("Consent text cannot be empty")
        if not granted_at:
            raise ValueError("Granted timestamp is required")

        self.user_id = user_id.strip()
        self.consent_type = consent_type.strip()
        self.consent_text = consent_text.strip()
        self.granted_at = granted_at
        # Hash IP address for privacy (GDPR compliance)
        self.ip_address = hash_ip_address(ip_address.strip() if ip_address else "unknown")
        self.user_agent = user_agent.strip() if user_agent else "unknown"
        self.status = status
        self.withdrawn_at = withdrawn_at
        self.metadata = metadata or {}

    def withdraw(self) -> None:
        """
        Withdraw consent.

        GDPR Art 7(3): Right to withdraw consent at any time.
        """
        self.status = ConsentStatus.WITHDRAWN
        self.withdrawn_at = datetime.now(timezone.utc)

    def is_active(self) -> bool:
        """
        Check if consent is currently active.

        Returns:
            True if consent is active and not withdrawn
        """
        return self.status == ConsentStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert consent record to dictionary for serialization.

        Returns:
            Dictionary representation of consent record
        """
        return {
            "user_id": self.user_id,
            "consent_type": self.consent_type,
            "consent_text": self.consent_text,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "status": self.status,
            "withdrawn_at": self.withdrawn_at.isoformat() if self.withdrawn_at else None,
            "metadata": self.metadata
        }

    def __repr__(self) -> str:
        """String representation of consent record"""
        status = "active" if self.is_active() else "withdrawn"
        return f"ConsentRecord(user_id='{self.user_id}', type='{self.consent_type}', status='{status}')"


class ConsentManager:
    """
    Consent management business logic.

    Handles consent lifecycle with GDPR compliance and audit trails.
    """

    def __init__(self, db_manager, audit_service):
        """
        Initialize consent manager with dependencies.

        Args:
            db_manager: Database manager for persistence
            audit_service: Audit service for compliance logging
        """
        self.db_manager = db_manager
        self.audit_service = audit_service

    async def record_consent(
        self,
        user_id: str,
        consent_type: str,
        consent_text: str,
        metadata: Dict[str, Any]
    ) -> ConsentRecord:
        """
        Record a new consent.

        GDPR Art 7(1): Consent must be specific, informed, and unambiguous.
        """
        # Input validation
        if not user_id or not user_id.strip():
            raise ValueError("User ID cannot be empty")

        if not consent_type or not consent_type.strip():
            raise ValueError("Consent type cannot be empty")

        if not consent_text or consent_text.strip() == "":
            raise ValueError("Consent text cannot be empty")

        # GDPR Art 7(1): Consent must be specific and informed
        consent_text_clean = consent_text.strip()
        if len(consent_text_clean) < 50:
            raise ValueError("Consent text must be specific and detailed (minimum 50 characters)")

        # Check for vague consent patterns
        vague_patterns = ["i agree", "i accept", "terms", "privacy policy", "yes", "ok", "i consent"]
        consent_lower = consent_text_clean.lower()
        if any(pattern in consent_lower for pattern in vague_patterns) and len(consent_text_clean) < 100:
            raise ValueError("Consent text must be specific - avoid generic 'I agree' statements")

        # Enhanced validation: Must explain data processing details
        required_elements = {
            "data_purpose": ["purpose", "why", "reason", "objective"],
            "data_type": ["data", "information", "personal data", "details"],
            "processing": ["processing", "use", "analyze", "store", "collect"],
            "retention": ["retain", "keep", "store", "period", "duration", "delete"]
        }

        missing_elements = []
        for element, keywords in required_elements.items():
            if not any(keyword in consent_lower for keyword in keywords):
                missing_elements.append(element)

        if missing_elements:
            raise ValueError(
                f"Consent text must explain: {', '.join(missing_elements)}. "
                "Include details about what data is processed, why, how long it's kept, and the purpose."
            )

        # Validate metadata
        if not metadata:
            metadata = {}

        # Ensure IP address is captured for audit trail
        if "ip" not in metadata:
            raise ValueError("IP address is required in metadata for compliance")

        # Ensure user agent is captured
        if "user_agent" not in metadata:
            raise ValueError("User agent is required in metadata for compliance")

        # Create consent record
        record = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            consent_text=consent_text.strip(),
            granted_at=datetime.now(timezone.utc),
            ip_address=metadata.get("ip", "unknown"),
            user_agent=metadata.get("user_agent", "unknown"),
            metadata=metadata
        )

        # Store in database
        consent_id = await self.db_manager.create_consent_record(record)

        # Log to audit trail
        if self.audit_service:
            await self.audit_service.log_consent_granted(
                user_id=user_id,
                consent_type=consent_type,
                timestamp=record.granted_at
            )

        return record

    async def verify_consent(self, user_id: str, consent_type: str) -> bool:
        """
        Verify if user has active consent for given type.
        """
        consent = await self.db_manager.get_active_consent(user_id, consent_type)
        return consent is not None and consent.status == ConsentStatus.ACTIVE

    async def withdraw_consent(self, user_id: str, consent_type: str) -> bool:
        """
        Withdraw consent for a user.

        GDPR Art 7(3): Right to withdraw consent at any time.
        """
        # Get existing consent
        consent = await self.db_manager.get_active_consent(user_id, consent_type)

        if not consent:
            return False

        # Withdraw the consent
        consent.withdraw()

        # Update in database
        await self.db_manager.update_consent_record(consent)

        # Log to audit trail
        if self.audit_service:
            await self.audit_service.log_consent_withdrawn(
                user_id=user_id,
                consent_type=consent_type,
                timestamp=consent.withdrawn_at
            )

        return True

    async def object_to_processing(
        self,
        user_id: str,
        consent_type: str,
        reason: str,
        category: str = "general"
    ) -> bool:
        """
        Handle objection to processing (GDPR Art 21).

        Users can object to processing even without prior consent.
        This creates a legal objection record that must be respected.

        Args:
            user_id: User identifier
            consent_type: Type of processing being objected to
            reason: Reason for objection
            category: Category of objection (marketing, analytics, etc.)

        Returns:
            True if objection recorded successfully
        """
        # Validate inputs
        if not user_id or not user_id.strip():
            raise ValueError("User ID cannot be empty")

        if not consent_type or not consent_type.strip():
            raise ValueError("Consent type cannot be empty")

        if not reason or len(reason.strip()) < 10:
            raise ValueError("Objection reason must be provided (minimum 10 characters)")

        # Create objection record (simplified as a special type of consent record)
        objection_record = ConsentRecord(
            user_id=user_id.strip(),
            consent_type=f"objection_{consent_type}",
            consent_text=f"OBJECTION TO PROCESSING: {reason.strip()}",
            granted_at=datetime.now(timezone.utc),
            ip_address="objection_filed",  # No IP for objections
            user_agent="objection_system",
            metadata={
                "objection_reason": reason.strip(),
                "objection_category": category,
                "objection_date": datetime.now(timezone.utc).isoformat(),
                "legal_basis": "GDPR_Article_21"
            }
        )

        # Store objection in database
        objection_id = await self.db_manager.create_consent_record(objection_record)

        # Log to audit trail
        if self.audit_service:
            await self.audit_service.log_consent_withdrawn(
                user_id=user_id,
                consent_type=f"objection_{consent_type}",
                timestamp=objection_record.granted_at
            )

        return True

    async def check_objection(self, user_id: str, consent_type: str) -> bool:
        """
        Check if user has objected to specific processing.

        Args:
            user_id: User identifier
            consent_type: Type of processing to check

        Returns:
            True if user has objected (processing must stop)
        """
        objection = await self.db_manager.get_active_consent(
            user_id,
            f"objection_{consent_type}"
        )
        return objection is not None