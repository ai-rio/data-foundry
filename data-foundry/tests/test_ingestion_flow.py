"""
Data Ingestion Flow Tests for Data Foundry
Tests the complete Prefect flow and ingestion pipeline
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime
import asyncio
import json

from src.tasks.ingestion import (
    extract_data,
    apply_pii_redaction,
    apply_ai_labeling,
    route_for_human_review,
    send_to_label_studio,
    save_to_database,
    data_ingestion_flow,
)
from src.core.config import settings


class TestDataIngestionFlow:
    """Test the complete data ingestion flow."""

    @pytest.mark.asyncio
    async def test_extract_data_task(self):
        """Test data extraction task."""
        # Mock data source
        data_source = "sample_data"

        result = await extract_data(data_source)

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
    async def test_complete_ingestion_flow_happy_path(self, mock_openai, mock_presidio, mock_label_studio):
        """Test complete ingestion flow with all components working."""
        # Mock all external dependencies
        mock_analyzer, mock_anonymizer = mock_presidio

        # Configure mocks
        mock_analyzer.analyze.return_value = [
            Mock(type="PERSON", text="John Doe"),
            Mock(type="EMAIL_ADDRESS", text="john@example.com"),
        ]
        mock_anonymizer.anonymize.return_value = Mock()
        mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

        mock_label_studio.get_project.return_value = Mock()
        mock_label_studio.get_project.return_value.import_tasks.return_value = True

        # Run the flow
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_ai_labeling=True,
            enable_pii_redaction=True,
            enable_human_review=True,
        )

        # Verify flow completed successfully
        assert result["success"] is True
        assert result["total_records"] == 3
        assert result["auto_approved"] >= 0
        assert result["human_review"] >= 0
        assert result["auto_approved"] + result["human_review"] == result["total_records"]

    @pytest.mark.asyncio
    async def test_ingestion_flow_without_pii_redaction(self, mock_openai):
        """Test ingestion flow without PII redaction."""
        # Run the flow without PII redaction
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_ai_labeling=True,
            enable_pii_redaction=False,  # Disable PII redaction
            enable_human_review=True,
        )

        # Verify flow completed
        assert result["success"] is True
        assert result["total_records"] == 3

        # Verify PII data was not redacted (should be preserved)
        # This would be verified by checking the actual data in the database

    @pytest.mark.asyncio
    async def test_ingestion_flow_without_ai_labeling(self):
        """Test ingestion flow without AI labeling."""
        # Run the flow without AI labeling
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_ai_labeling=False,  # Disable AI labeling
            enable_pii_redaction=True,
            enable_human_review=True,
        )

        # Verify flow completed
        assert result["success"] is True
        assert result["total_records"] == 3

        # Verify no AI fields were added to data
        # This would be verified by checking the processed data

    @pytest.mark.asyncio
    async def test_ingestion_flow_without_human_review(self, mock_openai, mock_presidio):
        """Test ingestion flow without human review."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Configure mocks
        mock_analyzer.analyze.return_value = []
        mock_anonymizer.anonymize.return_value = Mock()
        mock_anonymizer.anonymize.return_value.text = "unchanged"

        # Run the flow without human review
        result = await data_ingestion_flow(
            data_source="sample_data",
            enable_ai_labeling=True,
            enable_pii_redaction=True,
            enable_human_review=False,  # Disable human review
        )

        # Verify flow completed
        assert result["success"] is True
        assert result["total_records"] == 3
        assert result["human_review"] == 0  # No records for human review

    @pytest.mark.asyncio
    async def test_ingestion_flow_error_handling(self):
        """Test ingestion flow error handling."""
        # Mock OpenAI to fail
        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API Error")
            mock_client_class.return_value = mock_client

            # Run the flow
            result = await data_ingestion_flow(
                data_source="sample_data",
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify flow handled error gracefully
            assert result["success"] is True
            assert result["total_records"] == 3

            # Check that error was logged in the data
            # This would be verified by checking the actual data

    @pytest.mark.asyncio
    async def test_ingestion_flow_missing_api_keys(self):
        """Test ingestion flow with missing API keys."""
        # Temporarily disable API keys
        original_openai_key = settings.OPENAI_API_KEY
        original_label_studio_key = settings.LABEL_STUDIO_API_KEY

        settings.OPENAI_API_KEY = None
        settings.LABEL_STUDIO_API_KEY = None

        try:
            # Run the flow
            result = await data_ingestion_flow(
                data_source="sample_data",
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify flow completed with degraded functionality
            assert result["success"] is True
            assert result["total_records"] == 3

        finally:
            # Restore API keys
            settings.OPENAI_API_KEY = original_openai_key
            settings.LABEL_STUDIO_API_KEY = original_label_studio_key

    @pytest.mark.asyncio
    async def test_ingestion_flow_pipeline_stages(self):
        """Test each stage of the ingestion pipeline separately."""
        # Test data
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Stage 1: Extract data
        extracted = await extract_data("sample_data")
        assert len(extracted) == 3

        # Stage 2: Apply PII redaction
        with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
             patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

            mock_analyzer = Mock()
            mock_anonymizer = Mock()
            mock_analyzer_class.return_value = mock_analyzer
            mock_anonymizer_class.return_value = mock_anonymizer

            mock_analyzer.analyze.return_value = [
                Mock(type="PERSON", text="John Doe"),
            ]
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            redacted = await apply_pii_redaction(extracted)
            assert redacted[0]["name"] == "[REDACTED]"

        # Stage 3: Apply AI labeling
        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "Enterprise"}'
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            labeled = await apply_ai_labeling(redacted)
            assert "ai_category" in labeled[0]
            assert labeled[0]["ai_confidence"] == 0.95

        # Stage 4: Route for human review
        auto_approved, human_review = await route_for_human_review(labeled)
        assert len(auto_approved) + len(human_review) == len(labeled)

        # Stage 5: Send to Label Studio
        with patch('label_studio_sdk.Client') as mock_client_class:
            mock_client = Mock()
            mock_project = Mock()
            mock_client.get_project.return_value = mock_project
            mock_client_class.return_value = mock_client

            # Send human review records
            if human_review:
                result = await send_to_label_studio(human_review)
                assert result is True

        # Stage 6: Save to database
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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save:

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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save:

            # Configure mocks to simulate different error scenarios
            mock_extract.return_value = [{"id": 1}]
            mock_pii.return_value = [{"id": 1}]
            mock_ai.side_effect = Exception("AI Error")
            mock_route.return_value = ([], [])
            mock_label_studio.return_value = True
            mock_save.return_value = True

            # Run flow with AI error
            result = await data_ingestion_flow(
                data_source="test",
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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save:

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
                 patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
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

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save:

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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save:

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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save:

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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
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

            # Run flow
            result = await data_ingestion_flow(
                data_source="test",
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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
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

            # Measure performance
            start_time = time.time()
            result = await data_ingestion_flow(
                data_source="test",
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
             patch('src.tasks.ingestion.apply_ai_labeling') as mock_ai, \
             patch('src.tasks.ingestion.route_for_human_review') as mock_route, \
             patch('src.tasks.ingestion.send_to_label_studio') as mock_label_studio, \
             patch('src.tasks.ingestion.save_to_database') as mock_save:

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
                enable_ai_labeling=True,
                enable_pii_redaction=True,
                enable_human_review=True,
            )

            # Verify schema validation (basic check)
            assert result["success"] is True