"""
AML (Anti-Money Laundering) Enumeration Types

This module defines all enum types used in the AML service for controlled values,
ensuring data integrity and type safety across the application.

Enums defined:
- AMLRiskLevel: Transaction risk classification (LOW, MEDIUM, HIGH, CRITICAL)
- AMLTypology: FATF standard AML typologies (ML, TF, PEP, etc.)
- AMLRegulatoryFlag: Regulatory compliance flags
- AMLExpertDecision: Expert review decisions (AGREE, DISAGREE, NEEDS_CLARIFICATION)
- AMLExpertReviewStatus: Review workflow status
- AMLAgreementLevel: Cohen's Kappa interpretation levels
- AMLMethodologyStatus: Methodology lifecycle status

Reference: P01-001 (Schema Design), P01-002 (Migrations)
"""

from enum import Enum


class AMLRiskLevel(str, Enum):
    """
    AML Transaction Risk Level Classification.

    Risk levels for AML transaction labels, following industry standard
    tiered risk classification. Each level corresponds to specific
    regulatory response requirements.

    Thresholds (configurable per methodology):
    - LOW: 0.00 - 0.25 confidence for suspicious activity
    - MEDIUM: 0.25 - 0.50 confidence for suspicious activity
    - HIGH: 0.50 - 0.75 confidence for suspicious activity
    - CRITICAL: 0.75 - 1.00 confidence for suspicious activity
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AMLTypology(str, Enum):
    """
    FATF Standard AML Typologies.

    Based on Financial Action Task Force (FATF) money laundering and
    terrorist financing typologies. These are the primary categories
    for classifying suspicious transaction patterns.

    References:
    - FATF 40 Recommendations
    - FATF Methodology for Assessing Compliance
    """
    # Core FATF typologies
    ML = "ML"  # Money Laundering (general)
    TF = "TF"  # Terrorist Financing
    PEP = "PEP"  # Politically Exposed Persons

    # Financial crimes
    FRAUD = "FRAUD"  # Financial Fraud
    SANCTIONS = "SANCTIONS"  # Sanctions Evasion
    TAX_EVASION = "TAX_EVASION"  # Tax Evasion
    BRIBERY = "BRIBERY"  # Bribery and Corruption

    # Trade-based and organized crime
    SMUGGLING = "SMUGGLING"  # Trade-based Money Laundering / Smuggling
    DRUG_TRAFFICKING = "DRUG_TRAFFICKING"  # Drug Trafficking Proceeds
    HUMAN_TRAFFICKING = "HUMAN_TRAFFICKING"  # Human Trafficking Proceeds

    # Additional typologies
    PROLIFERATION = "PROLIFERATION"  # Proliferation Financing
    CYBERCRIME = "CYBERCRIME"  # Cybercrime Proceeds
    ENVIRONMENTAL = "ENVIRONMENTAL"  # Environmental Crimes


class AMLRegulatoryFlag(str, Enum):
    """
    AML Regulatory Compliance Flags.

    Flags indicating specific regulatory concerns or risk indicators
    that may require additional scrutiny or reporting.

    These flags are typically stored in the regulatory_flags JSONB column
    and can be combined for complex risk scenarios.
    """
    # Jurisdiction and sanctions
    HIGH_RISK_JURISDICTION = "HIGH_RISK_JURISDICTION"  # FATF grey/black list country
    SANCTIONS_MATCH = "SANCTIONS_MATCH"  # Match against sanctions lists

    # Suspicious patterns
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"  # General suspicious activity
    SHELL_COMPANY = "SHELL_COMPANY"  # Shell company involvement
    UNUSUAL_VOLUME = "UNUSUAL_VOLUME"  # Unusual transaction volume

    # Money laundering techniques
    STRUCTURING = "STRUCTURING"  # Smurfing / structuring transactions
    ROUND_TRIPPING = "ROUND_TRIPPING"  # Circular fund flows
    LAYERING = "LAYERING"  # Layering / complexity in transactions

    # Additional flags
    CASH_INTENSIVE = "CASH_INTENSIVE"  # Cash-intensive business
    RAPID_MOVEMENT = "RAPID_MOVEMENT"  # Rapid movement of funds
    THIRD_PARTY = "THIRD_PARTY"  # Third-party payments
    NO_APPARENT_PURPOSE = "NO_APPARENT_PURPOSE"  # No apparent business purpose


class AMLExpertDecision(str, Enum):
    """
    AML Expert Review Decision Types.

    Decisions made by human experts when reviewing AI-generated
    AML transaction labels. Used for calculating inter-rater
    agreement (Cohen's Kappa).
    """
    AGREE = "AGREE"  # Expert agrees with AI classification
    DISAGREE = "DISAGREE"  # Expert disagrees with AI classification
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"  # More information needed


class AMLExpertReviewStatus(str, Enum):
    """
    AML Expert Review Workflow Status.

    Status of a transaction label in the expert review workflow.
    Determines whether the label is ready for audit or requires
    additional review.
    """
    PENDING = "PENDING"  # Awaiting expert review
    AGREED = "AGREED"  # Expert agreed with AI label
    DISAGREED = "DISAGREED"  # Expert disagreed, may need re-labeling
    ESCALATED = "ESCALATED"  # Escalated to senior reviewer


class AMLAgreementLevel(str, Enum):
    """
    Cohen's Kappa Agreement Level Interpretation.

    Based on Landis & Koch (1977) interpretation scale for
    Cohen's Kappa coefficient measuring inter-rater agreement.

    Kappa ranges:
    - POOR: < 0.00 (less than chance agreement)
    - FAIR: 0.00 - 0.20
    - MODERATE: 0.21 - 0.40
    - SUBSTANTIAL: 0.41 - 0.60
    - PERFECT: 0.61 - 1.00 (near-perfect to perfect agreement)

    Note: For AML audit purposes, SUBSTANTIAL or PERFECT agreement
    is typically required for regulatory defensibility.
    """
    POOR = "POOR"  # Kappa < 0.00
    FAIR = "FAIR"  # Kappa 0.00 - 0.20
    MODERATE = "MODERATE"  # Kappa 0.21 - 0.40
    SUBSTANTIAL = "SUBSTANTIAL"  # Kappa 0.41 - 0.60
    PERFECT = "PERFECT"  # Kappa 0.61 - 1.00


class AMLMethodologyStatus(str, Enum):
    """
    AML Labeling Methodology Lifecycle Status.

    Tracks the lifecycle state of a labeling methodology version.
    Only one ACTIVE methodology should exist per tenant at a time.
    """
    DRAFT = "DRAFT"  # Methodology in development, not yet active
    ACTIVE = "ACTIVE"  # Currently active methodology for labeling
    ARCHIVED = "ARCHIVED"  # Previously used, now archived for audit trail
