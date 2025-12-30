"""
AML Labeling Prompt for AI-driven Transaction Classification

This module contains the FATF-aligned prompt for AI models to classify
financial transactions for Anti-Money Laundering (AML) compliance.

Features:
- FATF regulatory framework alignment
- FinCEN guidance integration
- Structured JSON response format
- Risk level classification (LOW, MEDIUM, HIGH, CRITICAL)
- FATF typology assignment
- Confidence scoring with explainability
- Few-shot learning examples

Reference: P01-004 (AML Labeling Task Implementation)
Regulatory References:
- FATF 40 Recommendations
- FATF Methodology for Assessing Compliance
- FinCEN BSA/AML Guidelines
"""

from enum import Enum
from typing import Dict, List, Any


class AMLPromptVersion(str, Enum):
    """AML prompt versions for versioning and A/B testing."""
    V1_0 = "1.0.0"


# Current prompt version
CURRENT_AML_PROMPT_VERSION = AMLPromptVersion.V1_0


# =============================================================================
# System Prompt for AML Analyst Role
# =============================================================================

AML_SYSTEM_PROMPT = """You are an expert Anti-Money Laundering (AML) Analyst with deep knowledge of:

1. FATF (Financial Action Task Force) 40 Recommendations
2. FATF Methodology for Assessing Technical Compliance and Effectiveness
3. FinCEN (Financial Crimes Enforcement Network) BSA/AML Guidelines
4. International sanctions regimes (OFAC, UN, EU)
5. Money laundering typologies and red flags
6. Terrorist financing patterns and indicators

Your Role:
- Analyze financial transactions for potential money laundering or terrorist financing
- Apply FATF typology classifications accurately
- Assign risk levels based on transaction characteristics and patterns
- Provide clear, auditable reasoning for regulatory compliance
- Ensure explainability for human expert review

Compliance Requirements:
- All assessments must be defensible under regulatory examination
- Reasoning must reference specific indicators and patterns
- Confidence scores must reflect actual certainty levels
- Low confidence requires explicit acknowledgment"""


# =============================================================================
# Main AML Labeling Prompt
# =============================================================================

AML_LABELING_PROMPT = """Analyze the following financial transaction for Anti-Money Laundering (AML) classification.

## Regulatory Framework

Apply the following frameworks in your analysis:

**FATF (Financial Action Task Force)**
- FATF 40 Recommendations for AML/CFT compliance
- FATF Methodology for assessing money laundering and terrorist financing risks
- FATF typologies for categorizing suspicious activity

**FinCEN (Financial Crimes Enforcement Network)**
- Bank Secrecy Act (BSA) requirements
- SAR (Suspicious Activity Report) filing criteria
- Red flag indicators for financial crimes

## Transaction Data

{transaction_data}

## Classification Instructions

Analyze this transaction and provide a JSON response with the following structure:

```json
{
    "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "typology": "FATF_TYPOLOGY_CODE",
    "confidence_score": 0.0-1.0,
    "reasoning": "Detailed explanation of your assessment",
    "regulatory_flags": ["FLAG1", "FLAG2"]
}
```

### Risk Level Definitions

- **LOW**: No significant suspicious indicators. Routine transaction consistent with expected activity.
- **MEDIUM**: Some unusual characteristics requiring monitoring. May warrant enhanced due diligence.
- **HIGH**: Multiple red flags or patterns consistent with money laundering typologies. Requires expert review.
- **CRITICAL**: Strong indicators of money laundering, terrorist financing, or sanctions evasion. Immediate escalation required.

### FATF Typology Codes

Use one of the following FATF-standard typology codes:

| Code | Description |
|------|-------------|
| ML | Money Laundering (general) - Funds derived from criminal activity |
| TF | Terrorist Financing - Funds supporting terrorist activities |
| PEP | Politically Exposed Persons - Transactions involving PEPs |
| FRAUD | Financial Fraud - Deceptive schemes for financial gain |
| SANCTIONS | Sanctions Evasion - Circumventing international sanctions |
| TAX_EVASION | Tax Evasion - Concealing taxable income or assets |
| BRIBERY | Bribery and Corruption - Illicit payments for influence |
| SMUGGLING | Trade-based Money Laundering / Smuggling |
| DRUG_TRAFFICKING | Drug Trafficking Proceeds |
| HUMAN_TRAFFICKING | Human Trafficking Proceeds |
| PROLIFERATION | Proliferation Financing - WMD-related financing |
| CYBERCRIME | Cybercrime Proceeds - Ransomware, hacking, etc. |
| ENVIRONMENTAL | Environmental Crimes - Wildlife trafficking, illegal logging |

### Regulatory Flags

Include applicable flags from:

- HIGH_RISK_JURISDICTION - FATF grey/black list country involvement
- SANCTIONS_MATCH - Potential match against sanctions lists
- SUSPICIOUS_PATTERN - Unusual transaction patterns
- SHELL_COMPANY - Shell company involvement suspected
- UNUSUAL_VOLUME - Transaction volume inconsistent with profile
- STRUCTURING - Possible smurfing/structuring to avoid thresholds
- ROUND_TRIPPING - Circular fund flows detected
- LAYERING - Complex layering of transactions
- CASH_INTENSIVE - Cash-intensive business patterns
- RAPID_MOVEMENT - Rapid movement of funds
- THIRD_PARTY - Third-party payments without clear purpose
- NO_APPARENT_PURPOSE - No apparent business purpose

### Confidence Score Guidelines

Your confidence_score should reflect your certainty:

- **0.90-1.00**: Very high confidence - Clear indicators, unambiguous classification
- **0.70-0.89**: High confidence - Strong indicators, minor uncertainties
- **0.60-0.69**: Moderate confidence - Some indicators, requires expert confirmation
- **0.40-0.59**: Low confidence - Limited indicators, expert review essential
- **0.00-0.39**: Very low confidence - Insufficient data, classification uncertain

**Important**: If confidence is below 0.60, explicitly state this in your reasoning and recommend expert review.

### Reasoning Requirements

Your reasoning MUST:

1. Be at least 50 characters long for audit trail
2. Reference specific transaction characteristics
3. Explain which indicators led to your risk assessment
4. Cite relevant FATF typology patterns if applicable
5. Note any missing data that affected confidence
6. Be written for potential regulatory examination

## Example Outputs

**Example 1: High Risk Transaction**
```json
{
    "risk_level": "HIGH",
    "typology": "ML",
    "confidence_score": 0.85,
    "reasoning": "Transaction exhibits classic layering behavior per FATF ML typology. Rapid movement of USD 47,500 through three shell companies in 48 hours, with final destination to high-risk jurisdiction (FATF grey list). Structuring pattern detected with amounts just below reporting threshold. No apparent business purpose documented.",
    "regulatory_flags": ["HIGH_RISK_JURISDICTION", "LAYERING", "STRUCTURING", "SHELL_COMPANY", "NO_APPARENT_PURPOSE"]
}
```

**Example 2: Critical Risk - Sanctions**
```json
{
    "risk_level": "CRITICAL",
    "typology": "SANCTIONS",
    "confidence_score": 0.92,
    "reasoning": "Direct wire transfer to entity with potential OFAC SDN list match. Beneficiary name and jurisdiction consistent with sanctioned party. Immediate escalation required per FinCEN guidance. Transaction should be held pending compliance review.",
    "regulatory_flags": ["SANCTIONS_MATCH", "HIGH_RISK_JURISDICTION"]
}
```

**Example 3: Low Risk Routine Transaction**
```json
{
    "risk_level": "LOW",
    "typology": "ML",
    "confidence_score": 0.78,
    "reasoning": "Routine payroll transaction consistent with customer profile. Amount and frequency match historical patterns. Sender and receiver in low-risk jurisdictions with established business relationship. No red flags or suspicious indicators detected.",
    "regulatory_flags": []
}
```

**Example 4: Low Confidence Assessment**
```json
{
    "risk_level": "MEDIUM",
    "typology": "FRAUD",
    "confidence_score": 0.45,
    "reasoning": "Some indicators of potential fraud but insufficient transaction history for high-confidence determination. First-time transaction with new counterparty. Unusual timing (off-hours processing) noted. Expert human review strongly recommended due to low confidence. Additional KYC information needed.",
    "regulatory_flags": ["SUSPICIOUS_PATTERN"]
}
```

Now analyze the transaction and provide your JSON response:"""


# =============================================================================
# Prompt Builder Function
# =============================================================================

def build_aml_labeling_prompt(
    transaction: Dict[str, Any],
    include_examples: bool = True,
    custom_context: str = None
) -> str:
    """
    Build the complete AML labeling prompt for a transaction.

    Args:
        transaction: Transaction data dictionary
        include_examples: Whether to include few-shot examples
        custom_context: Optional additional context

    Returns:
        Complete prompt string for AI model
    """
    # Format transaction data for prompt
    transaction_data = format_transaction_for_prompt(transaction)

    # Build prompt
    prompt = AML_LABELING_PROMPT.format(transaction_data=transaction_data)

    # Add custom context if provided
    if custom_context:
        prompt = f"{prompt}\n\n## Additional Context\n{custom_context}"

    return prompt


def format_transaction_for_prompt(transaction: Dict[str, Any]) -> str:
    """
    Format transaction data as readable text for prompt.

    SECURITY: Applies sanitization to prevent prompt injection attacks.
    All user-provided field values are sanitized before interpolation.

    Args:
        transaction: Transaction data dictionary

    Returns:
        Formatted transaction string
    """
    # Import sanitize_prompt_input for prompt injection protection
    from src.tasks.ingestion import sanitize_prompt_input

    lines = []

    # Core transaction fields
    field_labels = {
        "transaction_id": "Transaction ID",
        "amount": "Amount",
        "currency": "Currency",
        "sender_country": "Sender Country",
        "receiver_country": "Receiver Country",
        "sender_name": "Sender Name",
        "receiver_name": "Receiver Name",
        "timestamp": "Transaction Timestamp",
        "transaction_type": "Transaction Type",
        "account_type": "Account Type",
        "sender_account_age": "Sender Account Age",
        "transaction_frequency": "Transaction Frequency",
        "historical_avg_amount": "Historical Average Amount",
        "notes": "Transaction Notes/Memo"
    }

    for field, label in field_labels.items():
        if field in transaction and transaction[field] is not None:
            # Sanitize field value to prevent prompt injection
            safe_value = sanitize_prompt_input(transaction[field], max_length=200)
            lines.append(f"- **{label}**: {safe_value}")

    # Add any additional fields not in standard mapping
    standard_fields = set(field_labels.keys()) | {"id", "tenant_id"}
    for field, value in transaction.items():
        if field not in standard_fields and value is not None:
            # Convert field name to readable format
            readable_name = field.replace("_", " ").title()
            # Sanitize field value
            safe_value = sanitize_prompt_input(value, max_length=200)
            lines.append(f"- **{readable_name}**: {safe_value}")

    return "\n".join(lines) if lines else "No transaction data provided"


# =============================================================================
# Constants for Validation
# =============================================================================

AML_RISK_LEVELS = frozenset(["LOW", "MEDIUM", "HIGH", "CRITICAL"])

FATF_TYPOLOGIES = frozenset([
    "ML",  # Money Laundering
    "TF",  # Terrorist Financing
    "PEP",  # Politically Exposed Persons
    "FRAUD",  # Financial Fraud
    "SANCTIONS",  # Sanctions Evasion
    "TAX_EVASION",  # Tax Evasion
    "BRIBERY",  # Bribery and Corruption
    "SMUGGLING",  # Trade-based ML
    "DRUG_TRAFFICKING",  # Drug proceeds
    "HUMAN_TRAFFICKING",  # Human trafficking proceeds
    "PROLIFERATION",  # WMD financing
    "CYBERCRIME",  # Cybercrime proceeds
    "ENVIRONMENTAL"  # Environmental crimes
])

REGULATORY_FLAGS = frozenset([
    "HIGH_RISK_JURISDICTION",
    "SANCTIONS_MATCH",
    "SUSPICIOUS_PATTERN",
    "SHELL_COMPANY",
    "UNUSUAL_VOLUME",
    "STRUCTURING",
    "ROUND_TRIPPING",
    "LAYERING",
    "CASH_INTENSIVE",
    "RAPID_MOVEMENT",
    "THIRD_PARTY",
    "NO_APPARENT_PURPOSE"
])


def get_aml_prompt_metadata() -> Dict[str, Any]:
    """
    Get metadata about the AML prompt for versioning and audit.

    Returns:
        Dictionary with prompt metadata
    """
    return {
        "version": CURRENT_AML_PROMPT_VERSION.value,
        "risk_levels": list(AML_RISK_LEVELS),
        "typologies": list(FATF_TYPOLOGIES),
        "regulatory_flags": list(REGULATORY_FLAGS),
        "regulatory_frameworks": ["FATF", "FinCEN", "BSA"],
        "includes_examples": True,
        "min_reasoning_length": 50
    }
