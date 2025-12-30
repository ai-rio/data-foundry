"""
Test Suite for AML Labeling Task (TDD - P01-004)

This module contains comprehensive tests for the AML-specific apply_aml_labeling() task.
Tests follow TDD principles - written before implementation.

Test Categories:
1. Valid AML response handling
2. Low confidence (<0.6) routing to expert review
3. Invalid response handling
4. Response parsing and validation
5. Error handling (timeout, AI errors)
6. FATF alignment verification
7. Reasoning explainability validation
8. Edge cases

Reference: P01-004 (AML Labeling Task Implementation)
"""

import pytest
import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import sys

# Imports for testing
from src.models.aml_enums import AMLRiskLevel, AMLTypology, AMLExpertReviewStatus
from src.tasks.ingestion import (
    apply_aml_labeling,
    validate_aml_response,
    _process_aml_record,
    AML_RISK_LEVELS,
    FATF_TYPOLOGIES,
    AML_CONFIDENCE_THRESHOLD,
    MIN_REASONING_LENGTH
)

# Path for patching - AIService is imported dynamically inside the function
AI_SERVICE_PATH = 'src.services.ai_service.AIService'
PROMPT_BUILDER_PATH = 'src.core.prompts.aml_labeling_prompt.build_aml_labeling_prompt'


# ============================================================================
# Helper Functions
# ============================================================================

def create_mock_ai_response(content: dict, model: str = "gpt-4o") -> MagicMock:
    """Create a properly configured mock AI response."""
    mock_response = MagicMock()
    mock_response.content = json.dumps(content)
    mock_response.model = model
    mock_response.usage = MagicMock(
        total_tokens=150,
        prompt_tokens=100,
        completion_tokens=50
    )
    mock_response.cost = Decimal("0.001")
    mock_response.response_time_ms = 500.0
    mock_response.request_id = f"req_{id(content)}"
    mock_response.fallback_used = False
    mock_response.from_cache = False
    mock_response.retry_count = 0
    return mock_response


def create_mock_ai_service(response: MagicMock) -> MagicMock:
    """Create a properly configured mock AI service."""
    mock_service = MagicMock()
    mock_service.initialize = AsyncMock()
    mock_service.completion = AsyncMock(return_value=response)
    mock_service.aml_completion = AsyncMock(return_value=response)
    return mock_service


def mock_build_prompt(record: dict) -> str:
    """Mock prompt builder for testing."""
    return f"Mock AML prompt for transaction {record.get('id', 'unknown')}"


def mock_logger():
    """Create a mock logger for testing."""
    logger = MagicMock()
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def valid_aml_response() -> Dict[str, Any]:
    """Valid AML labeling response from AI service."""
    return {
        "risk_level": "HIGH",
        "typology": "ML",
        "confidence_score": 0.85,
        "reasoning": "Transaction exhibits layering behavior with rapid movement of funds through multiple accounts in high-risk jurisdictions. Pattern consistent with FATF ML typology indicators.",
        "regulatory_flags": ["HIGH_RISK_JURISDICTION", "LAYERING", "RAPID_MOVEMENT"]
    }


@pytest.fixture
def low_confidence_aml_response() -> Dict[str, Any]:
    """AML response with low confidence requiring expert review."""
    return {
        "risk_level": "MEDIUM",
        "typology": "FRAUD",
        "confidence_score": 0.45,
        "reasoning": "Some indicators of potential fraud but insufficient data to make high-confidence determination. Transaction pattern requires human expert review.",
        "regulatory_flags": ["SUSPICIOUS_PATTERN"]
    }


@pytest.fixture
def critical_risk_response() -> Dict[str, Any]:
    """Critical risk AML response."""
    return {
        "risk_level": "CRITICAL",
        "typology": "TF",
        "confidence_score": 0.92,
        "reasoning": "Strong indicators of terrorist financing. Direct transfer to designated entity. Immediate escalation required per FATF and FinCEN guidelines.",
        "regulatory_flags": ["SANCTIONS_MATCH", "HIGH_RISK_JURISDICTION"]
    }


@pytest.fixture
def sample_transaction_record() -> Dict[str, Any]:
    """Sample transaction record for labeling."""
    return {
        "id": "txn_001",
        "transaction_id": "TXN-2024-001234",
        "tenant_id": "tenant_001",
        "amount": 50000.00,
        "currency": "USD",
        "sender_country": "US",
        "receiver_country": "IR",
        "timestamp": datetime.utcnow().isoformat(),
        "account_type": "corporate",
        "transaction_type": "wire_transfer"
    }


@pytest.fixture
def invalid_risk_level_response() -> Dict[str, Any]:
    """Response with invalid risk level."""
    return {
        "risk_level": "EXTREME",  # Invalid - not in AMLRiskLevel
        "typology": "ML",
        "confidence_score": 0.75,
        "reasoning": "Some reasoning text that is long enough for validation requirements."
    }


@pytest.fixture
def invalid_typology_response() -> Dict[str, Any]:
    """Response with invalid typology."""
    return {
        "risk_level": "HIGH",
        "typology": "UNKNOWN_TYPE",  # Invalid - not in AMLTypology
        "confidence_score": 0.75,
        "reasoning": "Some reasoning text that is long enough for validation requirements."
    }


@pytest.fixture
def invalid_confidence_response() -> Dict[str, Any]:
    """Response with out-of-range confidence score."""
    return {
        "risk_level": "HIGH",
        "typology": "ML",
        "confidence_score": 1.5,  # Invalid - must be 0-1
        "reasoning": "Some reasoning text that is long enough for validation requirements."
    }


@pytest.fixture
def missing_reasoning_response() -> Dict[str, Any]:
    """Response with empty reasoning."""
    return {
        "risk_level": "HIGH",
        "typology": "ML",
        "confidence_score": 0.75,
        "reasoning": ""  # Invalid - must be non-empty
    }


# ============================================================================
# Test Class: Valid AML Response Handling (_process_aml_record)
# ============================================================================

class TestProcessAMLRecordValidResponse:
    """Tests for _process_aml_record() with valid AML responses."""

    @pytest.mark.asyncio
    async def test_valid_aml_response_returns_label(
        self,
        sample_transaction_record: Dict[str, Any],
        valid_aml_response: Dict[str, Any]
    ):
        """
        Test that valid AML response creates proper AMLTransactionLabel.

        Given: A transaction record and valid AI response
        When: _process_aml_record() is called
        Then: Returns record with correct AML classification values
        """
        mock_response = create_mock_ai_response(valid_aml_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert result["aml_risk_level"] == "HIGH"
        assert result["aml_typology"] == "ML"
        assert result["aml_confidence_score"] == 0.85
        assert "layering" in result["aml_reasoning"].lower()
        assert result["aml_expert_review_status"] == AMLExpertReviewStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_high_confidence_auto_approved(
        self,
        sample_transaction_record: Dict[str, Any],
        valid_aml_response: Dict[str, Any]
    ):
        """
        Test that high confidence (>=0.6) responses are auto-approved status.

        Given: A transaction with high confidence AI response (>=0.6)
        When: _process_aml_record() is called
        Then: Expert review status is PENDING (ready for bulk approval)
        """
        mock_response = create_mock_ai_response(valid_aml_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        # High confidence should be PENDING (awaiting bulk approval)
        assert result["aml_expert_review_status"] == AMLExpertReviewStatus.PENDING.value
        assert result["aml_requires_expert_review"] == False

    @pytest.mark.asyncio
    async def test_critical_risk_immediate_escalation(
        self,
        sample_transaction_record: Dict[str, Any],
        critical_risk_response: Dict[str, Any]
    ):
        """
        Test that CRITICAL risk transactions are immediately escalated.

        Given: A transaction with CRITICAL risk level
        When: _process_aml_record() is called
        Then: Expert review status is ESCALATED
        """
        mock_response = create_mock_ai_response(critical_risk_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert result["aml_risk_level"] == "CRITICAL"
        # CRITICAL risk should be ESCALATED for immediate attention
        assert result["aml_expert_review_status"] == AMLExpertReviewStatus.ESCALATED.value


# ============================================================================
# Test Class: Low Confidence Handling
# ============================================================================

class TestProcessAMLRecordLowConfidence:
    """Tests for _process_aml_record() with low confidence responses (<0.6)."""

    @pytest.mark.asyncio
    async def test_low_confidence_routes_to_expert_review(
        self,
        sample_transaction_record: Dict[str, Any],
        low_confidence_aml_response: Dict[str, Any]
    ):
        """
        Test that low confidence (<0.6) responses route to expert review.

        Given: AI response with confidence < 0.6
        When: _process_aml_record() is called
        Then: Expert review status is PENDING with requires_expert_review=True
        """
        mock_response = create_mock_ai_response(low_confidence_aml_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert result["aml_confidence_score"] < 0.6
        assert result["aml_requires_expert_review"] == True
        assert result["aml_expert_review_status"] == AMLExpertReviewStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_confidence_threshold_boundary_0_6(
        self,
        sample_transaction_record: Dict[str, Any]
    ):
        """
        Test boundary condition at confidence = 0.6.

        Given: AI response with confidence exactly 0.6
        When: _process_aml_record() is called
        Then: Should NOT require expert review (threshold is <0.6)
        """
        boundary_response = {
            "risk_level": "MEDIUM",
            "typology": "ML",
            "confidence_score": 0.6,  # Exactly at threshold
            "reasoning": "Borderline confidence determination with sufficient analysis context."
        }

        mock_response = create_mock_ai_response(boundary_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert result["aml_confidence_score"] == 0.6
        assert result["aml_requires_expert_review"] == False


# ============================================================================
# Test Class: Invalid Response Handling
# ============================================================================

class TestProcessAMLRecordInvalidResponse:
    """Tests for _process_aml_record() with invalid AI responses."""

    @pytest.mark.asyncio
    async def test_invalid_risk_level_sets_pending_status(
        self,
        sample_transaction_record: Dict[str, Any],
        invalid_risk_level_response: Dict[str, Any]
    ):
        """
        Test that invalid risk level sets status to PENDING for expert review.

        Given: AI response with invalid risk_level
        When: _process_aml_record() is called
        Then: Log error and set status PENDING (needs expert review)
        """
        mock_response = create_mock_ai_response(invalid_risk_level_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert "aml_validation_error" in result
        assert "risk_level" in result["aml_validation_error"].lower()
        assert result["aml_expert_review_status"] == AMLExpertReviewStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_invalid_typology_sets_pending_status(
        self,
        sample_transaction_record: Dict[str, Any],
        invalid_typology_response: Dict[str, Any]
    ):
        """
        Test that invalid typology sets status to PENDING for expert review.

        Given: AI response with invalid typology
        When: _process_aml_record() is called
        Then: Log error and set status PENDING (needs expert review)
        """
        mock_response = create_mock_ai_response(invalid_typology_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert "aml_validation_error" in result
        assert "typology" in result["aml_validation_error"].lower()

    @pytest.mark.asyncio
    async def test_confidence_out_of_range_sets_pending(
        self,
        sample_transaction_record: Dict[str, Any],
        invalid_confidence_response: Dict[str, Any]
    ):
        """
        Test that confidence score outside 0-1 range sets PENDING status.

        Given: AI response with confidence > 1.0 or < 0.0
        When: _process_aml_record() is called
        Then: Log error and set status PENDING
        """
        mock_response = create_mock_ai_response(invalid_confidence_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert "aml_validation_error" in result
        assert "confidence" in result["aml_validation_error"].lower()

    @pytest.mark.asyncio
    async def test_empty_reasoning_sets_pending(
        self,
        sample_transaction_record: Dict[str, Any],
        missing_reasoning_response: Dict[str, Any]
    ):
        """
        Test that empty reasoning sets PENDING status.

        Given: AI response with empty reasoning field
        When: _process_aml_record() is called
        Then: Log error and set status PENDING
        """
        mock_response = create_mock_ai_response(missing_reasoning_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert "aml_validation_error" in result
        assert "reasoning" in result["aml_validation_error"].lower()

    @pytest.mark.asyncio
    async def test_malformed_json_response_handles_gracefully(
        self,
        sample_transaction_record: Dict[str, Any]
    ):
        """
        Test that malformed JSON response is handled gracefully.

        Given: AI returns malformed JSON
        When: _process_aml_record() is called
        Then: Log error, set status PENDING
        """
        mock_response = MagicMock()
        mock_response.content = "Not valid JSON {broken"
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock(total_tokens=150)
        mock_response.cost = Decimal("0.001")
        mock_response.response_time_ms = 500.0
        mock_response.request_id = "req_malformed"
        mock_response.fallback_used = False
        mock_response.from_cache = False
        mock_response.retry_count = 0

        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert "aml_error" in result
        assert result["aml_expert_review_status"] == AMLExpertReviewStatus.PENDING.value


# ============================================================================
# Test Class: apply_aml_labeling Task Tests
# ============================================================================

class TestApplyAMLLabelingTask:
    """Tests for the full apply_aml_labeling() task with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_empty_transaction_list(self):
        """Test handling of empty transaction list."""
        # Empty list should return immediately without calling AI service
        # Patch the logger to avoid Prefect runtime context issues
        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()
            result = await apply_aml_labeling.fn([])
            assert result == []

    @pytest.mark.asyncio
    async def test_multiple_transactions_batch(
        self,
        sample_transaction_record: Dict[str, Any],
        valid_aml_response: Dict[str, Any]
    ):
        """Test batch processing of multiple transactions."""
        transactions = [
            {**sample_transaction_record, "id": f"txn_{i}"}
            for i in range(5)
        ]

        mock_response = create_mock_ai_response(valid_aml_response)
        mock_service = create_mock_ai_service(mock_response)

        # Patch the imports inside the task function
        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            # Patch AIService at the module level where it's imported
            with patch('src.services.ai_service.AIService', return_value=mock_service):
                result = await apply_aml_labeling.fn(transactions)

                assert len(result) == 5
                for record in result:
                    assert "aml_risk_level" in record

    @pytest.mark.asyncio
    async def test_ai_timeout_returns_retry_eligible(
        self,
        sample_transaction_record: Dict[str, Any]
    ):
        """
        Test that AI timeout marks record for retry.

        Given: AI service times out
        When: apply_aml_labeling() is called
        Then: Return with retry_eligible=True
        """
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock()
        mock_service.completion = AsyncMock(side_effect=asyncio.TimeoutError("AI request timed out"))
        mock_service.aml_completion = AsyncMock(side_effect=asyncio.TimeoutError("AI request timed out"))

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            with patch('src.services.ai_service.AIService', return_value=mock_service):
                result = await apply_aml_labeling.fn([sample_transaction_record])

                labeled_record = result[0]
                assert "aml_error" in labeled_record
                assert "timeout" in labeled_record["aml_error"].lower()
                assert labeled_record.get("aml_retry_eligible") == True

    @pytest.mark.asyncio
    async def test_ai_service_error_sets_escalated(
        self,
        sample_transaction_record: Dict[str, Any]
    ):
        """
        Test that AI service error sets status to ESCALATED.

        Given: AI service returns an error (non-timeout)
        When: apply_aml_labeling() is called
        Then: Set status ESCALATED
        """
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock()
        mock_service.completion = AsyncMock(side_effect=Exception("AI service unavailable"))
        mock_service.aml_completion = AsyncMock(side_effect=Exception("AI service unavailable"))

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            with patch('src.services.ai_service.AIService', return_value=mock_service):
                result = await apply_aml_labeling.fn([sample_transaction_record])

                labeled_record = result[0]
                assert "aml_error" in labeled_record
                assert labeled_record["aml_expert_review_status"] == AMLExpertReviewStatus.ESCALATED.value

    @pytest.mark.asyncio
    async def test_initialization_failure_handled(
        self,
        sample_transaction_record: Dict[str, Any]
    ):
        """
        Test that AI service initialization failure is handled.

        Given: AI service fails to initialize
        When: apply_aml_labeling() is called
        Then: Log error and set ESCALATED status
        """
        mock_service = MagicMock()
        mock_service.initialize = AsyncMock(side_effect=Exception("Failed to initialize"))

        with patch('src.tasks.ingestion.get_run_logger') as mock_get_logger:
            mock_get_logger.return_value = mock_logger()

            with patch('src.services.ai_service.AIService', return_value=mock_service):
                result = await apply_aml_labeling.fn([sample_transaction_record])

                labeled_record = result[0]
                assert "aml_error" in labeled_record


# ============================================================================
# Test Class: Response Parsing
# ============================================================================

class TestAMLResponseParsing:
    """Tests for AML response parsing and validation."""

    def test_validate_risk_level_valid(self):
        """Test that valid risk levels are accepted."""
        for level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            response = {
                "risk_level": level,
                "typology": "ML",
                "confidence_score": 0.8,
                "reasoning": "Test reasoning that meets minimum length requirements for validation."
            }
            is_valid, errors = validate_aml_response(response)
            assert is_valid, f"Risk level {level} should be valid, errors: {errors}"

    def test_validate_risk_level_invalid(self):
        """Test that invalid risk levels are rejected."""
        response = {
            "risk_level": "EXTREME",
            "typology": "ML",
            "confidence_score": 0.8,
            "reasoning": "Test reasoning that meets minimum length requirements for validation."
        }
        is_valid, errors = validate_aml_response(response)
        assert not is_valid
        assert any("risk_level" in e.lower() for e in errors)

    def test_validate_typology_valid_fatf(self):
        """Test that valid FATF typologies are accepted."""
        valid_typologies = ["ML", "TF", "PEP", "FRAUD", "SANCTIONS",
                           "TAX_EVASION", "BRIBERY", "SMUGGLING",
                           "DRUG_TRAFFICKING", "HUMAN_TRAFFICKING",
                           "PROLIFERATION", "CYBERCRIME", "ENVIRONMENTAL"]

        for typology in valid_typologies:
            response = {
                "risk_level": "HIGH",
                "typology": typology,
                "confidence_score": 0.8,
                "reasoning": "Test reasoning for FATF alignment that meets minimum length requirements."
            }
            is_valid, errors = validate_aml_response(response)
            assert is_valid, f"Typology {typology} should be valid, errors: {errors}"

    def test_validate_confidence_range(self):
        """Test confidence score validation (0.0-1.0)."""
        # Valid confidence scores
        for score in [0.0, 0.5, 1.0]:
            response = {
                "risk_level": "HIGH",
                "typology": "ML",
                "confidence_score": score,
                "reasoning": "Test reasoning that meets minimum length requirements for validation."
            }
            is_valid, errors = validate_aml_response(response)
            assert is_valid, f"Confidence {score} should be valid, errors: {errors}"

        # Invalid confidence scores
        for score in [-0.1, 1.1, 2.0]:
            response = {
                "risk_level": "HIGH",
                "typology": "ML",
                "confidence_score": score,
                "reasoning": "Test reasoning that meets minimum length requirements for validation."
            }
            is_valid, errors = validate_aml_response(response)
            assert not is_valid
            assert any("confidence" in e.lower() for e in errors)

    def test_validate_reasoning_non_empty(self):
        """Test that reasoning must be non-empty."""
        # Empty reasoning
        response = {
            "risk_level": "HIGH",
            "typology": "ML",
            "confidence_score": 0.8,
            "reasoning": ""
        }
        is_valid, errors = validate_aml_response(response)
        assert not is_valid
        assert any("reasoning" in e.lower() for e in errors)

        # Whitespace-only reasoning
        response["reasoning"] = "   "
        is_valid, errors = validate_aml_response(response)
        assert not is_valid


# ============================================================================
# Test Class: FATF Alignment
# ============================================================================

class TestFATFAlignment:
    """Tests for FATF regulatory alignment in AML labeling."""

    def test_prompt_includes_fatf_context(self):
        """Test that AML prompt includes FATF regulatory context."""
        from src.core.prompts.aml_labeling_prompt import AML_LABELING_PROMPT

        # Check FATF mention
        assert "FATF" in AML_LABELING_PROMPT

        # Check core typologies mentioned
        for typology in ["Money Laundering", "Terrorist Financing", "PEP"]:
            assert typology in AML_LABELING_PROMPT or typology.upper() in AML_LABELING_PROMPT

    def test_prompt_includes_fincen_context(self):
        """Test that AML prompt includes FinCEN regulatory context."""
        from src.core.prompts.aml_labeling_prompt import AML_LABELING_PROMPT

        assert "FinCEN" in AML_LABELING_PROMPT

    def test_prompt_includes_example_outputs(self):
        """Test that AML prompt includes example outputs for few-shot learning."""
        from src.core.prompts.aml_labeling_prompt import AML_LABELING_PROMPT

        # Check for example structure
        assert "example" in AML_LABELING_PROMPT.lower() or "Example" in AML_LABELING_PROMPT

    def test_prompt_specifies_json_response_format(self):
        """Test that AML prompt specifies JSON response format."""
        from src.core.prompts.aml_labeling_prompt import AML_LABELING_PROMPT

        assert "JSON" in AML_LABELING_PROMPT or "json" in AML_LABELING_PROMPT

        # Should specify required fields
        required_fields = ["risk_level", "typology", "confidence_score", "reasoning"]
        for field in required_fields:
            assert field in AML_LABELING_PROMPT


# ============================================================================
# Test Class: Explainability
# ============================================================================

class TestReasoningExplainability:
    """Tests for AI reasoning explainability requirements."""

    @pytest.mark.asyncio
    async def test_reasoning_includes_pattern_description(
        self,
        sample_transaction_record: Dict[str, Any],
        valid_aml_response: Dict[str, Any]
    ):
        """Test that reasoning includes description of suspicious patterns."""
        mock_response = create_mock_ai_response(valid_aml_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        reasoning = result["aml_reasoning"]
        # Reasoning should explain WHY, not just WHAT
        assert len(reasoning) > 50  # Minimum substantive reasoning

    def test_minimum_reasoning_length_validation(self):
        """Test that reasoning has minimum length for explainability."""
        # Too short reasoning
        response = {
            "risk_level": "HIGH",
            "typology": "ML",
            "confidence_score": 0.8,
            "reasoning": "Bad."  # Too short for audit trail
        }
        is_valid, errors = validate_aml_response(response)
        assert not is_valid
        assert any("reasoning" in e.lower() for e in errors)


# ============================================================================
# Test Class: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases in AML labeling."""

    @pytest.mark.asyncio
    async def test_transaction_with_missing_fields(
        self,
        valid_aml_response: Dict[str, Any]
    ):
        """Test handling of transaction with missing optional fields."""
        minimal_transaction = {
            "id": "txn_minimal",
            "transaction_id": "TXN-MIN-001",
            "tenant_id": "tenant_001"
        }

        # Adjust response for low confidence since data is minimal
        response_data = {
            "risk_level": "LOW",
            "typology": "ML",
            "confidence_score": 0.3,
            "reasoning": "Insufficient transaction data for detailed analysis. Low confidence due to missing fields. Expert review recommended."
        }

        mock_response = create_mock_ai_response(response_data)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=minimal_transaction,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        # Should still process with available data
        assert "aml_risk_level" in result

    @pytest.mark.asyncio
    async def test_regulatory_flags_parsing(
        self,
        sample_transaction_record: Dict[str, Any],
        valid_aml_response: Dict[str, Any]
    ):
        """Test that regulatory flags are properly parsed and stored."""
        mock_response = create_mock_ai_response(valid_aml_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        result = await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        assert "aml_regulatory_flags" in result
        flags = result["aml_regulatory_flags"]
        assert isinstance(flags, list)
        assert "HIGH_RISK_JURISDICTION" in flags


# ============================================================================
# Test Class: Integration with AIService
# ============================================================================

class TestAIServiceIntegration:
    """Tests for integration with AIService."""

    @pytest.mark.asyncio
    async def test_calls_aml_completion_with_correct_params(
        self,
        sample_transaction_record: Dict[str, Any],
        valid_aml_response: Dict[str, Any]
    ):
        """Test that _process_aml_record calls AIService.aml_completion correctly."""
        mock_response = create_mock_ai_response(valid_aml_response)
        mock_service = create_mock_ai_service(mock_response)
        logger = mock_logger()

        await _process_aml_record(
            record=sample_transaction_record,
            ai_service=mock_service,
            build_prompt=mock_build_prompt,
            system_prompt="Test system prompt",
            logger=logger
        )

        # Verify aml_completion or completion was called
        assert (mock_service.aml_completion.called or mock_service.completion.called)


# ============================================================================
# Configuration Constants Tests
# ============================================================================

class TestAMLLabelingConstants:
    """Tests for AML labeling configuration constants."""

    def test_aml_risk_levels_constant(self):
        """Test AML_RISK_LEVELS constant contains required levels."""
        required_levels = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert required_levels == set(AML_RISK_LEVELS)

    def test_aml_typologies_constant(self):
        """Test FATF_TYPOLOGIES constant contains required typologies."""
        required_typologies = {"ML", "TF", "PEP", "FRAUD", "SANCTIONS"}
        assert required_typologies.issubset(set(FATF_TYPOLOGIES))

    def test_confidence_threshold_constant(self):
        """Test AML_CONFIDENCE_THRESHOLD is properly defined."""
        assert AML_CONFIDENCE_THRESHOLD == 0.6
        assert 0 < AML_CONFIDENCE_THRESHOLD < 1

    def test_minimum_reasoning_length_constant(self):
        """Test MIN_REASONING_LENGTH constant for explainability."""
        assert MIN_REASONING_LENGTH >= 20  # Minimum for substantive reasoning
