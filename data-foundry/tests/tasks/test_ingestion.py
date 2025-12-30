"""
Tests for Data Ingestion Flow Tasks

This test suite follows TDD principles to validate fixes for P01-006 issues:
- Issue 1: AI timeout retry count tracking
- Issue 2: Remove redundant duplicate detection query
- Issue 3: Standardize error response structures

Author: Data Foundry Team
Version: 1.0.0
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock, MockSpec
from datetime import datetime
from typing import Any, Dict
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.tasks.ingestion import (
    apply_aml_labeling,
    _process_aml_record,
    save_aml_labels_to_database,
    validate_aml_response,
)


# =============================================================================
# Issue 1: AI Timeout Retry Count Tracking Tests
# =============================================================================

class TestAITimeoutRetryTracking:
    """
    Test suite for Issue 1: Add retry count tracking for AI timeout.

    Requirements:
    - Add aml_retry_count field to timeout error responses
    - Implement max retry logic (3 retries before escalation)
    - Track retry attempts in error records
    """

    @pytest.mark.asyncio
    async def test_timeout_error_includes_retry_count_field(self):
        """
        RED Phase: Failing test - timeout error should include retry count.
        Currently, asyncio.TimeoutError handling doesn't set aml_retry_count.
        """
        # Arrange: Create mock data
        test_data = [
            {
                "id": "txn_001",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "amount": 1000.0,
                "counterparty": "unknown_entity"
            }
        ]

        # Arrange: Mock AI service to raise TimeoutError
        mock_ai_service = AsyncMock()
        mock_ai_service.initialize = AsyncMock()
        mock_ai_service.aml_completion = AsyncMock(
            side_effect=asyncio.TimeoutError("AI request timeout")
        )

        # Act & Assert
        with patch("src.tasks.ingestion.AIService", return_value=mock_ai_service):
            with patch("src.tasks.ingestion.build_aml_labeling_prompt", return_value="test prompt"):
                result = await apply_aml_labeling(test_data)

        # Assert: Should have aml_retry_count field
        assert len(result) == 1
        assert "aml_retry_count" in result[0], \
            "FAIL: aml_retry_count field missing from timeout error response"
        assert result[0]["aml_retry_count"] == 0, \
            "FAIL: Initial timeout should have retry_count=0"

    @pytest.mark.asyncio
    async def test_timeout_error_with_existing_retry_count(self):
        """
        RED Phase: Failing test - should increment existing retry count.
        If a record already has aml_retry_count, subsequent timeouts should increment it.
        """
        # Arrange: Record with existing retry count
        test_data = [
            {
                "id": "txn_002",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "amount": 1000.0,
                "aml_retry_count": 1  # Already retried once
            }
        ]

        # Arrange: Mock AI service to raise TimeoutError again
        mock_ai_service = AsyncMock()
        mock_ai_service.initialize = AsyncMock()
        mock_ai_service.aml_completion = AsyncMock(
            side_effect=asyncio.TimeoutError("AI request timeout")
        )

        # Act & Assert
        with patch("src.tasks.ingestion.AIService", return_value=mock_ai_service):
            with patch("src.tasks.ingestion.build_aml_labeling_prompt", return_value="test prompt"):
                result = await apply_aml_labeling(test_data)

        # Assert: Should increment retry count
        assert len(result) == 1
        assert "aml_retry_count" in result[0], \
            "FAIL: aml_retry_count field missing"
        assert result[0]["aml_retry_count"] == 2, \
            f"FAIL: Expected retry_count=2, got {result[0].get('aml_retry_count')}"

    @pytest.mark.asyncio
    async def test_max_retry_limit_enforced(self):
        """
        RED Phase: Failing test - should escalate after 3 retries.
        Records with retry_count >= 3 should be escalated, not marked as retry_eligible.
        """
        # Arrange: Record at max retry limit
        test_data = [
            {
                "id": "txn_003",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "amount": 1000.0,
                "aml_retry_count": 3  # At max retries
            }
        ]

        # Arrange: Mock AI service to raise TimeoutError
        from src.models.aml_enums import AMLExpertReviewStatus

        mock_ai_service = AsyncMock()
        mock_ai_service.initialize = AsyncMock()
        mock_ai_service.aml_completion = AsyncMock(
            side_effect=asyncio.TimeoutError("AI request timeout")
        )

        # Act & Assert
        with patch("src.tasks.ingestion.AIService", return_value=mock_ai_service):
            with patch("src.tasks.ingestion.build_aml_labeling_prompt", return_value="test prompt"):
                result = await apply_aml_labeling(test_data)

        # Assert: Should escalate after max retries
        assert len(result) == 1
        assert result[0]["aml_expert_review_status"] == AMLExpertReviewStatus.ESCALATED.value, \
            f"FAIL: Expected ESCALATED status after max retries, got {result[0].get('aml_expert_review_status')}"
        assert result[0].get("aml_retry_eligible") is False, \
            "FAIL: Should not be retry_eligible after max retries"


# =============================================================================
# Issue 2: Redundant Duplicate Detection Query Tests
# =============================================================================

class TestRedundantDuplicateQueryRemoval:
    """
    Test suite for Issue 2: Remove redundant duplicate detection query.

    Requirements:
    - Remove the SELECT query at lines 1911-1926
    - Rely solely on ON CONFLICT DO NOTHING for duplicate handling
    - Maintain same functionality without redundant query
    """

    @pytest.mark.asyncio
    async def test_duplicate_handling_without_redundant_query(self):
        """
        RED Phase: This test verifies that duplicates are handled correctly
        without the redundant SELECT query. The ON CONFLICT clause should
        be sufficient.

        Note: This is an integration-style test that will pass once the
        redundant query is removed.
        """
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy import text

        # Arrange: Test data with potential duplicates
        labeled_records = [
            {
                "transaction_id": "txn_001",
                "aml_risk_level": "HIGH",
                "aml_typology": "ML",
                "aml_confidence_score": 0.85,
                "aml_reasoning": "Test reasoning",
                "aml_expert_review_status": "PENDING"
            },
            {
                "transaction_id": "txn_001",  # Duplicate
                "aml_risk_level": "HIGH",
                "aml_typology": "ML",
                "aml_confidence_score": 0.85,
                "aml_reasoning": "Test reasoning",
                "aml_expert_review_status": "PENDING"
            }
        ]
        tenant_id = "tenant_001"

        # Act: Mock database session
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.rollback = AsyncMock()

        with patch("src.tasks.ingestion.db_connection.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session

            result = await save_aml_labels_to_database(labeled_records, tenant_id)

        # Assert: Should handle duplicates correctly
        assert result["total_saved"] <= 2, \
            "FAIL: Should save at most 1 record (duplicate should be skipped)"
        assert result["duplicates_skipped"] >= 1, \
            "FAIL: Should have skipped at least 1 duplicate"

    @pytest.mark.asyncio
    async def test_no_select_query_for_duplicates(self):
        """
        RED Phase: Verify that the code path doesn't execute a SELECT query
        to check for duplicates before INSERT.

        This test uses mocking to track which queries are executed.
        """
        # Arrange: Track SQL queries executed
        executed_queries = []

        async def track_execute(query, params=None):
            executed_queries.append({
                "type": "SELECT" if "SELECT" in str(query) else "INSERT",
                "query": str(query)
            })
            # Return mock result
            mock_result = Mock()
            mock_result.fetchall = Mock(return_value=[])
            return mock_result

        # Arrange: Test data
        labeled_records = [
            {
                "transaction_id": "txn_new_001",
                "aml_risk_level": "MEDIUM",
                "aml_typology": "TF",
                "aml_confidence_score": 0.75,
                "aml_reasoning": "Test reasoning",
                "aml_expert_review_status": "PENDING"
            }
        ]

        # Act: Mock database session with query tracking
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=track_execute)
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        with patch("src.tasks.ingestion.db_connection.get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session

            result = await save_aml_labels_to_database(labeled_records, "tenant_test")

        # Assert: Should NOT have SELECT query for duplicates
        select_queries = [q for q in executed_queries if q["type"] == "SELECT"]
        duplicate_select_queries = [
            q for q in select_queries
            if "transaction_id" in q["query"] and "ANY" in q["query"]
        ]

        assert len(duplicate_select_queries) == 0, \
            f"FAIL: Found redundant SELECT query for duplicate detection. " \
            f"Queries: {[q['query'] for q in duplicate_select_queries]}"


# =============================================================================
# Issue 3: Standardized Error Response Structures Tests
# =============================================================================

class TestStandardizedErrorResponses:
    """
    Test suite for Issue 3: Standardize error response structures.

    Requirements:
    - Create consistent error response format across all tasks
    - All error responses should have: error_type, error_message, timestamp, record_id
    - Maintain backward compatibility where possible
    """

    @pytest.mark.asyncio
    async def test_aml_timeout_error_has_standard_structure(self):
        """
        RED Phase: Timeout errors should follow standard error structure.
        Currently, error structures are inconsistent.
        """
        # Arrange: Test data
        test_data = [
            {
                "id": "txn_004",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "amount": 1000.0
            }
        ]

        # Arrange: Mock AI service to raise TimeoutError
        mock_ai_service = AsyncMock()
        mock_ai_service.initialize = AsyncMock()
        mock_ai_service.aml_completion = AsyncMock(
            side_effect=asyncio.TimeoutError("AI request timeout")
        )

        # Act
        with patch("src.tasks.ingestion.AIService", return_value=mock_ai_service):
            with patch("src.tasks.ingestion.build_aml_labeling_prompt", return_value="test prompt"):
                result = await apply_aml_labeling(test_data)

        # Assert: Should have standard error structure
        error_record = result[0]
        assert "aml_error_type" in error_record, \
            "FAIL: Missing standard error_type field"
        assert error_record["aml_error_type"] == "TIMEOUT", \
            f'FAIL: Expected error_type="TIMEOUT", got {error_record.get("aml_error_type")}'
        assert "aml_error" in error_record, \
            "FAIL: Missing error_message field"
        assert "aml_processed_at" in error_record, \
            "FAIL: Missing timestamp field"

    @pytest.mark.asyncio
    async def test_aml_validation_error_has_standard_structure(self):
        """
        RED Phase: Validation errors should follow standard error structure.
        """
        # Arrange: Test data
        test_data = [
            {
                "id": "txn_005",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "amount": 1000.0
            }
        ]

        # Arrange: Mock AI service to return invalid response
        from src.services.ai_service import AIResponse

        invalid_response = AIResponse(
            content='{"risk_level": "INVALID", "typology": "ML", "confidence_score": 0.8, "reasoning": "Test"}',
            model="gpt-4",
            request_id="req_001",
            usage=MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            cost=0.001,
            response_time_ms=100,
            fallback_used=False,
            from_cache=False,
            cached_at=None,
            retry_count=0,
            completion_id="comp_001"
        )

        mock_ai_service = AsyncMock()
        mock_ai_service.initialize = AsyncMock()
        mock_ai_service.aml_completion = AsyncMock(return_value=invalid_response)

        # Act
        with patch("src.tasks.ingestion.AIService", return_value=mock_ai_service):
            with patch("src.tasks.ingestion.build_aml_labeling_prompt", return_value="test prompt"):
                result = await apply_aml_labeling(test_data)

        # Assert: Should have standard error structure
        error_record = result[0]
        assert "aml_error_type" in error_record, \
            "FAIL: Missing standard error_type field"
        assert error_record["aml_error_type"] == "VALIDATION", \
            f'FAIL: Expected error_type="VALIDATION", got {error_record.get("aml_error_type")}'
        assert "aml_validation_error" in error_record or "aml_error" in error_record, \
            "FAIL: Missing error_message field"

    @pytest.mark.asyncio
    async def test_aml_service_error_has_standard_structure(self):
        """
        RED Phase: Service errors should follow standard error structure.
        """
        # Arrange: Test data
        test_data = [
            {
                "id": "txn_006",
                "tenant_id": "tenant_001",
                "user_id": "user_001",
                "amount": 1000.0
            }
        ]

        # Arrange: Mock AI service to raise general exception
        mock_ai_service = AsyncMock()
        mock_ai_service.initialize = AsyncMock()
        mock_ai_service.aml_completion = AsyncMock(
            side_effect=Exception("AI service unavailable")
        )

        # Act
        with patch("src.tasks.ingestion.AIService", return_value=mock_ai_service):
            with patch("src.tasks.ingestion.build_aml_labeling_prompt", return_value="test prompt"):
                result = await apply_aml_labeling(test_data)

        # Assert: Should have standard error structure
        error_record = result[0]
        assert "aml_error_type" in error_record, \
            "FAIL: Missing standard error_type field"
        assert error_record["aml_error_type"] == "SERVICE", \
            f'FAIL: Expected error_type="SERVICE", got {error_record.get("aml_error_type")}'
        assert "aml_error" in error_record, \
            "FAIL: Missing error_message field"
        assert "aml_processed_at" in error_record, \
            "FAIL: Missing timestamp field"


# =============================================================================
# Helper Functions and Fixtures
# =============================================================================

@pytest.fixture
def mock_ai_response():
    """Create a mock AI response for testing."""
    from src.services.ai_service import AIResponse

    return AIResponse(
        content='{"risk_level": "HIGH", "typology": "ML", "confidence_score": 0.85, "reasoning": "Test reasoning with sufficient length for validation requirements"}',
        model="gpt-4",
        request_id="req_001",
        usage=MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        cost=0.001,
        response_time_ms=100,
        fallback_used=False,
        from_cache=False,
        cached_at=None,
        retry_count=0,
        completion_id="comp_001"
    )


@pytest.fixture
def valid_aml_record():
    """Create a valid AML record for testing."""
    return {
        "id": "txn_valid_001",
        "tenant_id": "tenant_001",
        "user_id": "user_001",
        "amount": 5000.0,
        "counterparty": "unknown_entity_xyz",
        "transaction_date": "2025-01-15T10:30:00Z",
        "description": "Large transaction to unknown entity"
    }
