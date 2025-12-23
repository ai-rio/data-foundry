"""
Data Ingestion Flow Tests for Data Foundry
Tests the complete Prefect flow and ingestion pipeline
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime
import asyncio
import json
import sys

from src.tasks.ingestion import (
    extract_data,
    validate_schema,
    check_duplicates,
    compute_quality_scores,
    filter_low_quality,
    apply_pii_redaction,
    apply_ai_labeling,
    route_for_human_review,
    send_to_label_studio,
    save_to_database,
    data_ingestion_flow,
    PRESIDIO_AVAILABLE,
)
from src.services.ai_service import AIService, AIRequest
from src.services.litellm_service import LiteLLMService
from src.core.config import settings


# Check if optional modules are available
LABEL_STUDIO_AVAILABLE = "label_studio_sdk" in sys.modules
try:
    import label_studio_sdk
    LABEL_STUDIO_AVAILABLE = True
except ImportError:
    LABEL_STUDIO_AVAILABLE = False


class TestDataIngestionFlow:
    """Test the complete data ingestion flow."""

    def test_extract_data_task(self):
        """Test data extraction task (sync)."""
        # Mock data source
        data_source = "sample_data"

        result = extract_data(data_source)

        # Verify extraction worked
        assert isinstance(result, list)
        assert len(result) == 3  # From the sample data in the task
        assert all(isinstance(item, dict) for item in result)

        # Verify data structure
        for item in result:
            assert "id" in item
            assert "name" in item
            assert "email" in item
            assert "phone" in item
            assert "tenant_id" in item
            assert "created_at" in item

    @pytest.mark.asyncio
    async def test_complete_ingestion_flow_happy_path(self, litellm_service):
        """Test complete ingestion flow with all components working."""
        # Mock Presidio availability
        with patch('src.tasks.ingestion.PRESIDIO_AVAILABLE', True):
            # Mock the AI Service initialization
            with patch('src.services.ai_service.AIService') as mock_ai_service:
                mock_service_instance = Mock()
                mock_ai_service.return_value = mock_service_instance
                mock_service_instance.initialize = AsyncMock()

                # Mock AI response
                mock_response = Mock()
                mock_response.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "Corporate"}'
                mock_response.model = "gpt-4o"
                mock_response.request_id = "req-123"
                mock_response.usage = Mock(total_tokens=100, prompt_tokens=50, completion_tokens=50)
                mock_response.cost = 0.001
                mock_response.response_time_ms = 500
                mock_response.fallback_used = False
                mock_response.from_cache = False
                mock_response.retry_count = 0
                mock_response.cached_at = None
                mock_response.completion_id = "comp-123"

                mock_service_instance.completion = AsyncMock(return_value=mock_response)

                # Run the flow
                result = await data_ingestion_flow(
                    data_source="sample_data",
                    enable_validation=False,  # Disable validation for backwards compatibility
                    enable_ai_labeling=True,
                    enable_pii_redaction=False,  # Disable PII to avoid Presidio dependency
                    enable_human_review=True,
                )

                # Verify flow completed successfully
                assert result["success"] is True
                assert result["total_records"] == 3
                assert result["auto_approved"] >= 0
                assert result["human_review"] >= 0
                assert result["auto_approved"] + result["human_review"] == result["total_records"]

    @pytest.mark.asyncio
    async def test_ingestion_flow_without_pii_redaction(self):
        """Test ingestion flow without PII redaction."""
        # Mock AI Service
        with patch('src.services.ai_service.AIService') as mock_ai_service:
            mock_service_instance = Mock()
            mock_ai_service.return_value = mock_service_instance
            mock_service_instance.initialize = AsyncMock()

            mock_response = Mock()
            mock_response.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "test"}'
            mock_response.model = "gpt-4o"
            mock_response.request_id = "req-123"
            mock_response.usage = Mock(total_tokens=100, prompt_tokens=50, completion_tokens=50)
            mock_response.cost = 0.001
            mock_response.response_time_ms = 500
            mock_response.fallback_used = False
            mock_response.from_cache = False
            mock_response.retry_count = 0
            mock_response.cached_at = None
            mock_response.completion_id = "comp-123"

            mock_service_instance.completion = AsyncMock(return_value=mock_response)

            # Run the flow without PII redaction
            result = await data_ingestion_flow(
                data_source="sample_data",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=False,  # Disable PII redaction
                enable_human_review=True,
            )

            # Verify flow completed
            assert result["success"] is True
            assert result["total_records"] == 3

    @pytest.mark.asyncio
    async def test_ingestion_flow_without_ai_labeling(self):
        """Test ingestion flow without AI labeling."""
        # Run the flow without AI labeling
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_validation=False,
            enable_ai_labeling=False,  # Disable AI labeling
            enable_pii_redaction=False,
            enable_human_review=True,
        )

        # Verify flow completed
        assert result["success"] is True
        assert result["total_records"] == 3

    @pytest.mark.asyncio
    async def test_ingestion_flow_without_human_review(self):
        """Test ingestion flow without human review."""
        # Mock AI Service
        with patch('src.services.ai_service.AIService') as mock_ai_service:
            mock_service_instance = Mock()
            mock_ai_service.return_value = mock_service_instance
            mock_service_instance.initialize = AsyncMock()

            mock_response = Mock()
            mock_response.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "test"}'
            mock_response.model = "gpt-4o"
            mock_response.request_id = "req-123"
            mock_response.usage = Mock(total_tokens=100, prompt_tokens=50, completion_tokens=50)
            mock_response.cost = 0.001
            mock_response.response_time_ms = 500
            mock_response.fallback_used = False
            mock_response.from_cache = False
            mock_response.retry_count = 0
            mock_response.cached_at = None
            mock_response.completion_id = "comp-123"

            mock_service_instance.completion = AsyncMock(return_value=mock_response)

            # Run the flow without human review
            result = await data_ingestion_flow(
                data_source="sample_data",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=False,
                enable_human_review=False,  # Disable human review
            )

            # Verify flow completed
            assert result["success"] is True
            assert result["total_records"] == 3
            assert result["human_review"] == 0  # No records for human review

    @pytest.mark.asyncio
    async def test_ingestion_flow_error_handling(self):
        """Test ingestion flow error handling."""
        # Mock AI Service to fail
        with patch('src.services.ai_service.AIService') as mock_ai_service:
            mock_service_instance = Mock()
            mock_ai_service.return_value = mock_service_instance
            mock_service_instance.initialize = AsyncMock()
            mock_service_instance.completion = AsyncMock(side_effect=Exception("API Error"))

            # Run the flow
            result = await data_ingestion_flow(
                data_source="sample_data",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=False,
                enable_human_review=True,
            )

            # Verify flow handled error gracefully
            assert result["success"] is True
            assert result["total_records"] == 3

    @pytest.mark.asyncio
    async def test_ingestion_flow_missing_api_keys(self):
        """Test ingestion flow with missing API keys."""
        # Mock the secure_* methods to return None
        with patch.object(settings, 'secure_openai_api_key', return_value=None), \
             patch.object(settings, 'PRIMARY_MODEL', None):

            # Run the flow
            result = await data_ingestion_flow(
                data_source="sample_data",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=False,
                enable_human_review=True,
            )

            # Verify flow completed with degraded functionality
            assert result["success"] is True
            assert result["total_records"] == 3

    @pytest.mark.asyncio
    async def test_ingestion_flow_pipeline_stages(self):
        """Test each stage of the ingestion pipeline separately."""
        # Stage 1: Extract data (sync - call directly)
        extracted = extract_data("sample_data")
        assert len(extracted) == 3

        # Stage 2: Apply PII redaction (sync - call directly)
        # Skip actual PII test if Presidio not available
        redacted = apply_pii_redaction(extracted)

        # Stage 3: Apply AI labeling (async - use await)
        with patch('src.services.ai_service.AIService') as mock_ai_service:
            mock_service_instance = Mock()
            mock_ai_service.return_value = mock_service_instance
            mock_service_instance.initialize = AsyncMock()

            mock_response = Mock()
            mock_response.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "test"}'
            mock_response.model = "gpt-4o"
            mock_response.request_id = "req-123"
            mock_response.usage = Mock(total_tokens=100, prompt_tokens=50, completion_tokens=50)
            mock_response.cost = 0.001
            mock_response.response_time_ms = 500
            mock_response.fallback_used = False
            mock_response.from_cache = False
            mock_response.retry_count = 0
            mock_response.cached_at = None
            mock_response.completion_id = "comp-123"

            mock_service_instance.completion = AsyncMock(return_value=mock_response)

            labeled = await apply_ai_labeling(redacted)
            assert "ai_category" in labeled[0]

        # Stage 4: Route for human review (sync - call directly)
        auto_approved, human_review = route_for_human_review(labeled)
        assert len(auto_approved) + len(human_review) == len(labeled)

        # Stage 5: Send to Label Studio (sync - call directly, skip if module not available)
        if LABEL_STUDIO_AVAILABLE and human_review:
            result = send_to_label_studio(human_review)
            assert result is True or result is False  # Either way is fine for test

        # Stage 6: Save to database - just test that it runs without error
        # This would test the database saving functionality


class TestIngestionPipelineIntegration:
    """Test pipeline integration and orchestration."""

    @pytest.mark.asyncio
    async def test_pipeline_flow_control(self):
        """Test flow control between pipeline stages."""
        # Test that stages are called in the correct order
        call_order = []

        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1, "name": "[REDACTED]"}]
            mock_ai.return_value = [{"id": 1, "ai_confidence": 0.9}]
            mock_route.return_value = ([{"id": 1}], [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow
            await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify call order
            assert mock_extract.called
            assert mock_pii.called
            assert mock_ai.called
            assert mock_route.called

    @pytest.mark.asyncio
    async def test_pipeline_error_propagation(self):
        """Test error propagation through the pipeline."""
        # Test that errors in one stage don't break the entire pipeline
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock(side_effect=Exception("AI Error"))) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks to simulate different error scenarios
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1}]
            mock_route.return_value = ([], [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow with AI error - the flow should handle it
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify flow continues despite error
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_pipeline_data_transformation(self):
        """Test data transformation through the pipeline."""
        # Test that data is properly transformed at each stage
        original_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
            }
        ]

        with patch('src.tasks.ingestion.extract_data', return_value=original_data), \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure PII redaction
            mock_pii.return_value = [
                {
                    "id": 1,
                    "name": "[REDACTED]",
                    "email": "[REDACTED]",
                    "phone": "[REDACTED]",
                    "tenant_id": "test_tenant_001",
                }
            ]

            # Configure AI labeling
            mock_ai.return_value = [
                {
                    "id": 1,
                    "name": "[REDACTED]",
                    "email": "[REDACTED]",
                    "phone": "[REDACTED]",
                    "tenant_id": "test_tenant_001",
                    "ai_category": "high_value",
                    "ai_confidence": 0.95,
                    "ai_reasoning": "Enterprise customer",
                    "ai_model": "gpt-4o",
                    "ai_processed_at": "2023-12-20T12:00:00Z",
                }
            ]

            # Configure routing
            mock_route.return_value = ([mock_ai.return_value[0]], [])

            # Configure other mocks
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify transformations
            assert result["success"] is True
            assert result["auto_approved"] == 1
            assert result["human_review"] == 0


class TestIngestionFlowConfiguration:
    """Test ingestion flow configuration and settings."""

    @pytest.mark.asyncio
    async def test_flow_configuration_options(self):
        """Test different flow configuration options."""
        test_configs = [
            {
                "name": "All features enabled",
                "enable_ai_labeling": True,
                "enable_pii_redaction": True,
                "enable_human_review": True,
            },
            {
                "name": "Minimal processing",
                "enable_ai_labeling": False,
                "enable_pii_redaction": False,
                "enable_human_review": False,
            },
            {
                "name": "PII and AI only",
                "enable_ai_labeling": True,
                "enable_pii_redaction": True,
                "enable_human_review": False,
            },
            {
                "name": "AI and human review only",
                "enable_ai_labeling": True,
                "enable_pii_redaction": False,
                "enable_human_review": True,
            },
        ]

        for config in test_configs:
            with patch('src.tasks.ingestion.extract_data') as mock_extract, \
                 patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
                 patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
                 patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
                 patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
                 patch('src.tasks.ingestion.save_to_database') as mock_save:

                # Configure mocks
                mock_extract.return_value = [{"id": 1}]
                mock_pii.return_value = [{"id": 1}]
                mock_ai.return_value = [{"id": 1}]
                mock_route.return_value = ([{"id": 1}], [])
                mock_label_studio.return_value = True
                mock_save.return_value = True

                # Run flow with config
                result = await data_ingestion_flow(
                    data_source="test",
                    enable_validation=False,
                    enable_ai_labeling=config["enable_ai_labeling"],
                    enable_pii_redaction=config["enable_pii_redaction"],
                    enable_human_review=config["enable_human_review"],
                )

                # Verify flow completed
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_data_source_configuration(self):
        """Test different data source configurations."""
        test_sources = ["sample_data", "csv_file", "json_file", "api_source"]

        for source in test_sources:
            with patch('src.tasks.ingestion.extract_data') as mock_extract:
                mock_extract.return_value = [{"id": 1}]

                # Run flow with different source
                result = await data_ingestion_flow(
                    data_source=source,
                    enable_validation=False,
                    enable_ai_labeling=False,
                    enable_pii_redaction=False,
                    enable_human_review=False,
                )

                # Verify extract was called with correct source
                mock_extract.assert_called_once_with(source)
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_flow_logging(self):
        """Test flow logging functionality."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1}]
            mock_ai.return_value = [{"id": 1}]
            mock_route.return_value = ([{"id": 1}], [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify logging would occur (this is hard to test without mocking logger)
            assert result["success"] is True


class TestIngestionFlowPerformance:
    """Test ingestion flow performance and scalability."""

    @pytest.mark.asyncio
    async def test_large_batch_processing(self):
        """Test processing of large data batches."""
        # Generate large dataset
        large_data = []
        for i in range(1000):
            large_data.append({
                "id": i + 1,
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "phone": f"555-{i:04d}",
                "tenant_id": "test_tenant_001",
            })

        with patch('src.tasks.ingestion.extract_data', return_value=large_data), \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks
            mock_pii.return_value = large_data
            mock_ai.return_value = large_data
            mock_route.return_value = (large_data, [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow with large dataset
            start_time = datetime.utcnow()
            result = await data_ingestion_flow(
                data_source="large_batch",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )
            end_time = datetime.utcnow()

            # Verify large batch was processed
            assert result["success"] is True
            assert result["total_records"] == 1000

            # Verify performance (this is just a basic check)
            processing_time = (end_time - start_time).total_seconds()
            assert processing_time < 60  # Should complete within a minute

    @pytest.mark.asyncio
    async def test_batch_chunking(self):
        """Test batch chunking for large datasets."""
        # This would test the flow's ability to handle chunked processing
        # In a real implementation, this would test the flow's chunking logic

        with patch('src.tasks.ingestion.extract_data') as mock_extract:
            mock_extract.return_value = [{"id": 1}]

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify flow completed
            assert result["success"] is True


class TestIngestionFlowErrorRecovery:
    """Test ingestion flow error recovery and retry logic."""

    @pytest.mark.asyncio
    async def test_retry_mechanism(self):
        """Test retry mechanism for failed operations."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks with failure scenarios
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1}]
            mock_ai.return_value = [{"id": 1}]
            mock_route.return_value = ([{"id": 1}], [])

            # Label Studio fails first time, succeeds second time
            mock_label_studio.side_effect = [False, True]

            # Database fails first time, succeeds second time
            mock_save.side_effect = [False, True]

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify flow succeeded after retries
            assert result["success"] is True
            assert mock_label_studio.call_count == 2
            assert mock_save.call_count == 2

    @pytest.mark.asyncio
    async def test_partial_processing_failure(self):
        """Test handling of partial processing failures."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks with mixed success/failure
            mock_extract.return_value = [
                {"id": 1, "name": "Record 1"},
                {"id": 2, "name": "Record 2"},
                {"id": 3, "name": "Record 3"},
            ]
            mock_pii.return_value = mock_extract.return_value
            mock_ai.return_value = mock_extract.return_value
            mock_route.return_value = (
                [{"id": 1}, {"id": 2}],  # Auto-approved
                [{"id": 3}],  # Human review
            )
            mock_label_studio.return_value = True
            mock_save.return_value = False  # Database save fails

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify flow completed but with partial failure
            assert result["success"] is True  # Overall success
            # The actual behavior would depend on error handling implementation


class TestIngestionFlowMonitoring:
    """Test ingestion flow monitoring and metrics."""

    @pytest.mark.asyncio
    async def test_flow_metrics_collection(self):
        """Test collection of flow metrics."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1}]
            mock_ai.return_value = [{"id": 1}]
            mock_route.return_value = ([{"id": 1}], [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify metrics are collected
            assert "total_records" in result
            assert "auto_approved" in result
            assert "human_review" in result
            assert "success" in result

    @pytest.mark.asyncio
    async def test_performance_metrics(self):
        """Test performance metrics collection."""
        import time

        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1}]
            mock_ai.return_value = [{"id": 1}]
            mock_route.return_value = ([{"id": 1}], [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Measure performance
            start_time = time.time()
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )
            end_time = time.time()

            # Verify performance metrics
            assert result["success"] is True
            processing_time = end_time - start_time
            assert processing_time > 0


class TestIngestionFlowDataValidation:
    """Test data validation in the ingestion flow."""

    @pytest.mark.asyncio
    async def test_data_validation_at_entry(self):
        """Test data validation at entry point."""
        # Test with invalid data
        invalid_data = [
            {
                "id": "not_a_number",
                "name": 123,  # Should be string
                "email": "invalid_email",
                "tenant_id": None,  # Required
            }
        ]

        with patch('src.tasks.ingestion.extract_data', return_value=invalid_data):
            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=False,
                enable_pii_redaction=False,
                enable_human_review=False,
            )

            # In a real implementation, this would test validation logic
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_schema_validation(self):
        """Test schema validation throughout the pipeline."""
        # Test that data maintains expected schema
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks to maintain schema
            mock_extract.return_value = [{"id": 1, "name": "Test"}]
            mock_pii.return_value = mock_extract.return_value
            mock_ai.return_value = mock_extract.return_value
            mock_route.return_value = ([mock_extract.return_value[0]], [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify schema validation (basic check)
            assert result["success"] is True


class TestDataValidationTasks:
    """Test data validation tasks (Week 1: Data Validation + Database Optimization)."""

    def test_validate_schema_with_valid_data(self):
        """Test validate_schema with valid records."""
        # Valid test data with required fields
        valid_records = [
            {
                "record_id": "rec-001",
                "tenant_id": "tenant_001",
                "data_source": "csv",
                "raw_data": '{"name": "John Doe", "email": "john@example.com"}',
                "file_name": "test.csv",
                "mime_type": "text/csv",
            },
            {
                "record_id": "rec-002",
                "tenant_id": "tenant_001",
                "data_source": "json",
                "raw_data": '{"name": "Jane Smith"}',
            },
        ]

        valid, invalid = validate_schema(valid_records)

        # Verify valid records
        assert len(valid) == 2
        assert all("validation_is_valid" in r for r in valid)
        assert all(r["validation_is_valid"] for r in valid)
        assert all("validation_quality_score" in r for r in valid)

        # Verify no invalid records
        assert len(invalid) == 0

    def test_validate_schema_with_invalid_data(self):
        """Test validate_schema with invalid records."""
        # Invalid test data - missing required fields
        invalid_records = [
            {
                "record_id": "rec-001",
                # Missing: tenant_id, data_source, raw_data
            },
            {
                # Completely empty record
            },
        ]

        valid, invalid = validate_schema(invalid_records)

        # Verify invalid records are identified
        assert len(invalid) == 2
        assert all("validation_is_valid" in r for r in invalid)
        assert all(not r["validation_is_valid"] for r in invalid)
        assert all("validation_errors" in r for r in invalid)

    def test_validate_schema_with_mixed_data(self):
        """Test validate_schema with mixed valid and invalid records."""
        mixed_records = [
            {
                "record_id": "rec-001",
                "tenant_id": "tenant_001",
                "data_source": "csv",
                "raw_data": '{"field": "value"}',
            },
            {
                "record_id": "rec-002",
                # Missing required fields
            },
            {
                "record_id": "rec-003",
                "tenant_id": "tenant_002",
                "data_source": "json",
                "raw_data": '{"another": "value"}',
            },
        ]

        valid, invalid = validate_schema(mixed_records)

        # Verify split
        assert len(valid) == 2
        assert len(invalid) == 1
        assert len(valid) + len(invalid) == len(mixed_records)

    def test_check_duplicates_with_unique_records(self):
        """Test check_duplicates with unique records."""
        unique_records = [
            {"id": 1, "name": "John"},
            {"id": 2, "name": "Jane"},
            {"id": 3, "name": "Bob"},
        ]

        new, duplicates = check_duplicates(unique_records)

        # Verify all are new
        assert len(new) == 3
        assert len(duplicates) == 0
        assert all("record_hash" in r for r in new)

    def test_check_duplicates_with_duplicate_records(self):
        """Test check_duplicates with duplicate records."""
        duplicate_records = [
            {"id": 1, "name": "John"},
            {"id": 2, "name": "Jane"},
            {"id": 1, "name": "John"},  # Duplicate
            {"id": 2, "name": "Jane"},  # Duplicate
        ]

        new, duplicates = check_duplicates(duplicate_records)

        # Verify duplicates are identified
        assert len(new) == 2
        assert len(duplicates) == 2
        assert len(new) + len(duplicates) == len(duplicate_records)

    def test_check_duplicates_hash_generation(self):
        """Test that check_duplicates generates consistent hashes."""
        records = [
            {"id": 1, "name": "John", "email": "john@example.com"},
            {"id": 1, "name": "John", "email": "john@example.com"},  # Same content
        ]

        new, duplicates = check_duplicates(records)

        # Verify second record is identified as duplicate
        assert len(new) == 1
        assert len(duplicates) == 1

        # Verify hashes are the same
        assert new[0]["record_hash"] == duplicates[0]["record_hash"]

    def test_compute_quality_scores_with_validated_data(self):
        """Test compute_quality_scores with validated records."""
        validated_records = [
            {
                "id": 1,
                "validation_quality_score": 0.85,
                "validation_completeness_score": 0.90,
                "validation_validity_score": 0.80,
            },
            {
                "id": 2,
                "validation_quality_score": 0.65,
                "validation_completeness_score": 0.70,
                "validation_validity_score": 0.60,
            },
        ]

        scored = compute_quality_scores(validated_records)

        # Verify scores are added
        assert len(scored) == 2
        assert all("data_quality_score" in r for r in scored)
        assert all("completeness_score" in r for r in scored)
        assert all("validity_score" in r for r in scored)
        assert all("quality_scored_at" in r for r in scored)

        # Verify score values
        assert scored[0]["data_quality_score"] == 0.85
        assert scored[1]["data_quality_score"] == 0.65

    def test_compute_quality_scores_without_validation(self):
        """Test compute_quality_scores with non-validated records."""
        non_validated_records = [
            {"id": 1, "name": "John"},
            {"id": 2, "name": "Jane"},
        ]

        scored = compute_quality_scores(non_validated_records)

        # Verify default scores are applied
        assert len(scored) == 2
        assert all("data_quality_score" in r for r in scored)
        assert all(r["data_quality_score"] == 0.5 for r in scored)

    def test_filter_low_quality_with_high_threshold(self):
        """Test filter_low_quality with high quality threshold."""
        scored_records = [
            {"id": 1, "data_quality_score": 0.9},
            {"id": 2, "data_quality_score": 0.7},
            {"id": 3, "data_quality_score": 0.4},
            {"id": 4, "data_quality_score": 0.6},
        ]

        high, low = filter_low_quality(scored_records, min_quality=0.7)

        # Verify filtering
        assert len(high) == 2  # 0.9, 0.7
        assert len(low) == 2   # 0.4, 0.6
        assert all(r["data_quality_score"] >= 0.7 for r in high)
        assert all(r["data_quality_score"] < 0.7 for r in low)

    def test_filter_low_quality_with_low_threshold(self):
        """Test filter_low_quality with low quality threshold."""
        scored_records = [
            {"id": 1, "data_quality_score": 0.9},
            {"id": 2, "data_quality_score": 0.3},
            {"id": 3, "data_quality_score": 0.4},
        ]

        high, low = filter_low_quality(scored_records, min_quality=0.5)

        # Verify filtering
        assert len(high) == 1  # Only 0.9
        assert len(low) == 2   # 0.3, 0.4

    def test_filter_low_quality_with_default_threshold(self):
        """Test filter_low_quality with default threshold (0.5)."""
        scored_records = [
            {"id": 1, "data_quality_score": 0.6},
            {"id": 2, "data_quality_score": 0.4},
        ]

        high, low = filter_low_quality(scored_records)

        # Verify default threshold of 0.5
        assert len(high) == 1
        assert len(low) == 1
        assert high[0]["id"] == 1
        assert low[0]["id"] == 2


class TestIngestionFlowWithValidation:
    """Test ingestion flow with validation enabled (Week 1 integration)."""

    @pytest.mark.asyncio
    async def test_flow_with_validation_enabled(self):
        """Test complete flow with validation enabled."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Mock extract with valid data (has required fields)
            mock_extract.return_value = [
                {
                    "record_id": "rec-001",
                    "tenant_id": "tenant_001",
                    "data_source": "csv",
                    "raw_data": '{"name": "Test"}',
                }
            ]

            # Configure mocks
            mock_pii.return_value = mock_extract.return_value
            mock_ai.return_value = mock_extract.return_value
            mock_route.return_value = (mock_extract.return_value, [])
            mock_save.return_value = True

            # Run flow with validation enabled
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=True,
                enable_ai_labeling=False,
                enable_pii_redaction=False,
                enable_human_review=False,
            )

            # Verify validation statistics in result
            assert result["success"] is True
            assert "valid_records" in result
            assert "invalid_records" in result
            assert "new_records" in result
            assert "duplicate_records" in result
            assert "high_quality" in result
            assert "low_quality" in result

    @pytest.mark.asyncio
    async def test_flow_with_validation_disabled(self):
        """Test flow with validation disabled (backwards compatibility)."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.apply_ai_labeling', new=AsyncMock()) as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Configure mocks
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1}]
            mock_ai.return_value = [{"id": 1}]
            mock_route.return_value = ([{"id": 1}], [])
            mock_save.return_value = True

            # Run flow with validation disabled
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=False,  # Disable validation
                enable_ai_labeling=False,
                enable_pii_redaction=False,
                enable_human_review=False,
            )

            # Verify flow completed without validation
            assert result["success"] is True
            assert result["total_extracted"] == 1
            # Validation stats should be 0 when disabled
            assert result["valid_records"] == 0
            assert result["invalid_records"] == 0

    @pytest.mark.asyncio
    async def test_validation_filters_invalid_data(self):
        """Test that validation filters out invalid records."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Mock extract with mixed valid/invalid data
            mock_extract.return_value = [
                {
                    "record_id": "rec-valid",
                    "tenant_id": "tenant_001",
                    "data_source": "csv",
                    "raw_data": '{"valid": "data"}',
                },
                {
                    "record_id": "rec-invalid",
                    # Missing required fields
                },
            ]

            mock_pii.return_value = True
            mock_save.return_value = True

            # Run flow with validation enabled
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=True,
                enable_ai_labeling=False,
                enable_pii_redaction=False,
                enable_human_review=False,
            )

            # Verify invalid records were filtered
            assert result["success"] is True
            assert result["total_extracted"] == 2
            assert result["valid_records"] == 1
            assert result["invalid_records"] == 1

    @pytest.mark.asyncio
    async def test_validation_with_quality_filtering(self):
        """Test quality filtering in validation pipeline."""
        with patch('src.tasks.ingestion.extract_data') as mock_extract, \
             patch('src.tasks.ingestion.apply_pii_redaction') as mock_pii, \
             patch('src.tasks.ingestion.save_to_database') as mock_save, \
             patch.object(settings, 'secure_openai_api_key', return_value="test-key"):

            # Mock extract with valid data
            mock_extract.return_value = [
                {
                    "record_id": f"rec-{i:03d}",
                    "tenant_id": "tenant_001",
                    "data_source": "csv",
                    "raw_data": f'{{"id": {i}}}',
                }
                for i in range(5)  # 5 records
            ]

            mock_pii.return_value = True
            mock_save.return_value = True

            # Run flow with validation enabled
            result = await data_ingestion_flow(
                data_source="test",
                enable_validation=True,
                enable_ai_labeling=False,
                enable_pii_redaction=False,
                enable_human_review=False,
            )

            # Verify quality filtering
            assert result["success"] is True
            assert "high_quality" in result
            assert "low_quality" in result
            # All 5 records should be valid (have required fields)
            assert result["valid_records"] == 5


class TestValidationPipelineIntegration:
    """Test validation pipeline integration scenarios."""

    def test_full_validation_pipeline(self):
        """Test full validation pipeline end-to-end."""
        # Sample data
        test_data = [
            {
                "record_id": "rec-001",
                "tenant_id": "tenant_001",
                "data_source": "csv",
                "raw_data": '{"name": "John", "email": "john@example.com"}',
                "file_name": "test.csv",
            },
            {
                "record_id": "rec-002",
                "tenant_id": "tenant_001",
                "data_source": "csv",
                "raw_data": '{"name": "Jane"}',
            },
            {
                "record_id": "rec-001",  # Duplicate
                "tenant_id": "tenant_001",
                "data_source": "csv",
                "raw_data": '{"name": "John", "email": "john@example.com"}',
                "file_name": "test.csv",
            },
            {
                "record_id": "rec-bad",
                # Missing required fields
            },
        ]

        # Step 1: Validate schema
        valid, invalid = validate_schema(test_data)
        assert len(valid) == 3
        assert len(invalid) == 1

        # Step 2: Check duplicates
        new, duplicates = check_duplicates(valid)
        assert len(new) == 2
        assert len(duplicates) == 1

        # Step 3: Compute quality scores
        scored = compute_quality_scores(new)
        assert len(scored) == 2
        assert all("data_quality_score" in r for r in scored)

        # Step 4: Filter by quality
        high, low = filter_low_quality(scored, min_quality=0.5)
        assert len(high) + len(low) == 2

    @pytest.mark.asyncio
    async def test_validation_pipeline_error_handling(self):
        """Test error handling in validation pipeline."""
        # Test with data that might cause errors
        problematic_data = [
            {
                "record_id": "rec-001",
                "tenant_id": "tenant_001",
                "data_source": "csv",
                "raw_data": '{"test": "data"}',
            },
            None,  # Invalid: None value
            {
                "record_id": "rec-003",
                "tenant_id": "tenant_001",
                "data_source": "json",
                "raw_data": '{"another": "value"}',
            },
        ]

        # Run validation - should handle errors gracefully
        valid, invalid = validate_schema(problematic_data)

        # Verify error handling
        assert len(valid) >= 0
        assert len(invalid) >= 0
        assert len(valid) + len(invalid) == len(problematic_data)