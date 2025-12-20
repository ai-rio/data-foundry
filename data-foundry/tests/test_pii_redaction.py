"""
PII Redaction Tests for Data Foundry
Tests Microsoft Presidio integration and PII detection
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.tasks.ingestion import apply_pii_redaction
from src.core.config import settings


class TestPIIRedaction:
    """Test PII redaction functionality."""

    @pytest.mark.asyncio
    async def test_pii_redaction_with_presidio(self, mock_presidio):
        """Test PII redaction using Microsoft Presidio."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Sample data with PII
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        # Configure mock analyzer to return PII findings
        mock_analyzer.analyze.return_value = [
            Mock(type="PERSON", text="John Doe"),
            Mock(type="EMAIL_ADDRESS", text="john@example.com"),
            Mock(type="PHONE_NUMBER", text="555-1234"),
        ]

        # Configure mock anonymizer to redact PII
        mock_anonymizer.anonymize.return_value = Mock()
        mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

        # Call the PII redaction function
        with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
             patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

            result = await apply_pii_redaction(sample_data)

        # Verify the analyzer was called for each PII field
        assert mock_analyzer.analyze.call_count == 3  # name, email, phone

        # Verify anonymizer was called for each PII field
        assert mock_anonymizer.anonymize.call_count == 3

        # Check that PII was redacted
        assert result[0]["name"] == "[REDACTED]"
        assert result[0]["email"] == "[REDACTED]"
        assert result[0]["phone"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_redaction_partial(self, mock_presidio):
        """Test partial PII redaction (some fields contain PII, others don't)."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Mixed data
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",  # Has PII
                "email": "john@example.com",  # Has PII
                "company": "Tech Corp",  # No PII
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        # Configure mock analyzer
        mock_analyzer.analyze.side_effect = [
            [Mock(type="PERSON", text="John Doe")],  # name
            [Mock(type="EMAIL_ADDRESS", text="john@example.com")],  # email
            [],  # company (no PII)
        ]

        # Configure mock anonymizer
        mock_anonymizer.anonymize.return_value = Mock()
        mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

        with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
             patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

            result = await apply_pii_redaction(sample_data)

        # Verify only PII fields were redacted
        assert result[0]["name"] == "[REDACTED]"
        assert result[0]["email"] == "[REDACTED]"
        assert result[0]["company"] == "Tech Corp"  # Unchanged

    @pytest.mark.asyncio
    async def test_pii_redaction_no_pii_detected(self, mock_presidio):
        """Test data processing when no PII is detected."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Data without PII
        sample_data = [
            {
                "id": 1,
                "company": "Tech Corp",
                "department": "Engineering",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        # Configure mock analyzer to return no PII
        mock_analyzer.analyze.return_value = []

        # Mock anonymizer (shouldn't be called)
        mock_anonymizer.anonymize.return_value = Mock()
        mock_anonymizer.anonymize.return_value.text = "unchanged"

        with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
             patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

            result = await apply_pii_redaction(sample_data)

        # Verify analyzer was called
        assert mock_analyzer.analyze.call_count == 0  # No fields to check

        # Verify data is unchanged
        assert result[0]["company"] == "Tech Corp"
        assert result[0]["department"] == "Engineering"

    @pytest.mark.asyncio
    async def test_pii_redaction_presidio_not_available(self):
        """Test graceful handling when Presidio is not available."""
        # Sample data
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        # Call without Presidio (should return data unchanged)
        result = await apply_pii_redaction(sample_data)

        # Verify data is unchanged
        assert result[0]["name"] == "John Doe"
        assert result[0]["email"] == "john@example.com"
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_pii_redaction_empty_data(self):
        """Test PII redaction with empty data."""
        # Empty data
        sample_data = []

        # Call PII redaction
        result = await apply_pii_redaction(sample_data)

        # Verify empty result
        assert result == []

    @pytest.mark.asyncio
    async def test_pii_redaction_single_field_record(self):
        """Test PII redaction with records having only one field."""
        # Sample data
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
             patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

            mock_analyzer = Mock()
            mock_anonymizer = Mock()
            mock_analyzer_class.return_value = mock_analyzer
            mock_anonymizer_class.return_value = mock_anonymizer

            # Configure analyzer
            mock_analyzer.analyze.return_value = [
                Mock(type="PERSON", text="John Doe")
            ]
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            result = await apply_pii_redaction(sample_data)

        # Verify PII was redacted
        assert result[0]["name"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_redaction_presidio_error_handling(self):
        """Test error handling when Presidio encounters errors."""
        # Sample data
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
             patch('presidio_anonymizer.AnonymizerEngine'):

            mock_analyzer = Mock()
            mock_analyzer_class.return_value = mock_analyzer

            # Configure analyzer to raise an exception
            mock_analyzer.analyze.side_effect = Exception("Presidio error")

            # Call PII redaction (should handle error gracefully)
            result = await apply_pii_redaction(sample_data)

        # Verify data is returned unchanged on error
        assert result[0]["name"] == "John Doe"
        assert result[0]["email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_pii_redaction_multiple_record_types(self):
        """Test PII redaction with different record types."""
        # Mixed data types
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            },
            {
                "id": 2,
                "company": "Tech Corp",
                "website": "https://techcorp.com",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:01:00Z",
            },
            {
                "id": 3,
                "name": "Jane Smith",
                "ssn": "123-45-6789",  # Sensitive PII
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:02:00Z",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
             patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

            mock_analyzer = Mock()
            mock_anonymizer = Mock()
            mock_analyzer_class.return_value = mock_analyzer
            mock_anonymizer_class.return_value = mock_anonymizer

            # Configure analyzer for different scenarios
            def mock_analyze(text, language="en"):
                if "John Doe" in text or "Jane Smith" in text:
                    return [Mock(type="PERSON", text=text)]
                elif "john@example.com" in text:
                    return [Mock(type="EMAIL_ADDRESS", text=text)]
                elif "555-1234" in text:
                    return [Mock(type="PHONE_NUMBER", text=text)]
                elif "123-45-6789" in text:
                    return [Mock(type="US_SSN", text=text)]
                return []

            mock_analyzer.analyze.side_effect = mock_analyze

            # Configure anonymizer
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            result = await apply_pii_redaction(sample_data)

        # Verify all PII was redacted
        # Record 1
        assert result[0]["name"] == "[REDACTED]"
        assert result[0]["email"] == "[REDACTED]"
        assert result[0]["phone"] == "[REDACTED]"

        # Record 2 (no PII)
        assert result[1]["company"] == "Tech Corp"
        assert result[1]["website"] == "https://techcorp.com"

        # Record 3
        assert result[2]["name"] == "[REDACTED]"
        assert result[2]["ssn"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_redaction_preserves_metadata(self):
        """Test that PII redaction preserves non-PII metadata."""
        # Sample data with metadata
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "metadata": {
                    "source": "csv",
                    "batch_id": "batch_123",
                    "created_by": "system",
                },
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
             patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

            mock_analyzer = Mock()
            mock_anonymizer = Mock()
            mock_analyzer_class.return_value = mock_analyzer
            mock_anonymizer_class.return_value = mock_anonymizer

            # Configure mocks
            mock_analyzer.analyze.return_value = [
                Mock(type="PERSON", text="John Doe"),
                Mock(type="EMAIL_ADDRESS", text="john@example.com"),
            ]
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            result = await apply_pii_redaction(sample_data)

        # Verify metadata is preserved
        assert result[0]["id"] == 1
        assert result[0]["metadata"] == {
            "source": "csv",
            "batch_id": "batch_123",
            "created_by": "system",
        }
        assert result[0]["tenant_id"] == "test_tenant_001"
        assert result[0]["created_at"] == "2023-12-20T12:00:00Z"

        # Verify PII fields were redacted
        assert result[0]["name"] == "[REDACTED]"
        assert result[0]["email"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_redaction_configuration_options(self, pii_sample_data):
        """Test PII redaction with different configuration options."""
        # Test with different field configurations
        test_cases = [
            {
                "name": "Only name field",
                "fields": ["name"],
                "expected_redacted": ["name"],
                "unchanged": ["email", "phone", "credit_card"],
            },
            {
                "name": "All PII fields",
                "fields": ["name", "email", "phone"],
                "expected_redacted": ["name", "email", "phone"],
                "unchanged": ["credit_card", "address"],
            },
            {
                "name": "Only specific PII types",
                "fields": ["credit_card", "ssn"],
                "expected_redacted": ["credit_card", "ssn"],
                "unchanged": ["name", "email", "phone"],
            },
        ]

        for test_case in test_cases:
            with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
                 patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

                mock_analyzer = Mock()
                mock_anonymizer = Mock()
                mock_analyzer_class.return_value = mock_analyzer
                mock_anonymizer_class.return_value = mock_anonymizer

                # Configure analyzer to detect PII in specified fields
                def mock_analyze(text, language="en"):
                    if any(field in test_case["fields"] for field in ["name"] if field in text):
                        return [Mock(type="PERSON", text=text)]
                    elif any(field in test_case["fields"] for field in ["email"] if field in text):
                        return [Mock(type="EMAIL_ADDRESS", text=text)]
                    elif any(field in test_case["fields"] for field in ["phone"] if field in text):
                        return [Mock(type="PHONE_NUMBER", text=text)]
                    elif any(field in test_case["fields"] for field in ["credit_card"] if field in text):
                        return [Mock(type="CREDIT_CARD", text=text)]
                    elif any(field in test_case["fields"] for field in ["ssn"] if field in text):
                        return [Mock(type="US_SSN", text=text)]
                    return []

                mock_analyzer.analyze.side_effect = mock_analyze

                # Configure anonymizer
                mock_anonymizer.anonymize.return_value = Mock()
                mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

                # Prepare test data with only specified fields
                test_data = []
                for i, record in enumerate(pii_sample_data):
                    test_record = {"id": i + 1, "tenant_id": "test_tenant_001"}
                    for field in test_case["fields"]:
                        if field in record:
                            test_record[field] = record[field]
                    test_data.append(test_record)

                result = await apply_pii_redaction(test_data)

                # Verify PII was redacted correctly
                for record in result:
                    for field in test_case["expected_redacted"]:
                        if field in record:
                            assert record[field] == "[REDACTED]"

                    for field in test_case["unchanged"]:
                        if field in record:
                            # Check that original value is preserved
                            original_value = next(
                                (r[field] for r in pii_sample_data if field in r),
                                None
                            )
                            assert record[field] == original_value


class TestPIIDetection:
    """Test PII detection capabilities."""

    @pytest.mark.asyncio
    async def test_pii_detection_credit_card(self, mock_presidio):
        """Test credit card number detection."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Test credit card detection
        test_data = [
            {
                "id": 1,
                "credit_card": "4111-1111-1111-1111",  # Valid test credit card
                "tenant_id": "test_tenant_001",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
             patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

            mock_analyzer.analyze.return_value = [
                Mock(type="CREDIT_CARD", text="4111-1111-1111-1111")
            ]
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            result = await apply_pii_redaction(test_data)

        assert result[0]["credit_card"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_detection_ssn(self, mock_presidio):
        """Test SSN detection."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Test SSN detection
        test_data = [
            {
                "id": 1,
                "ssn": "123-45-6789",
                "tenant_id": "test_tenant_001",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
             patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

            mock_analyzer.analyze.return_value = [
                Mock(type="US_SSN", text="123-45-6789")
            ]
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            result = await apply_pii_redaction(test_data)

        assert result[0]["ssn"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_detection_multiple_types(self, mock_presidio):
        """Test detection of multiple PII types in a single record."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Test multiple PII types
        test_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",
                "ssn": "123-45-6789",
                "credit_card": "4111-1111-1111-1111",
                "tenant_id": "test_tenant_001",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
             patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

            mock_analyzer.analyze.return_value = [
                Mock(type="PERSON", text="John Doe"),
                Mock(type="EMAIL_ADDRESS", text="john@example.com"),
                Mock(type="PHONE_NUMBER", text="555-1234"),
                Mock(type="US_SSN", text="123-45-6789"),
                Mock(type="CREDIT_CARD", text="4111-1111-1111-1111"),
            ]
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            result = await apply_pii_redaction(test_data)

        # Verify all PII types were redacted
        assert result[0]["name"] == "[REDACTED]"
        assert result[0]["email"] == "[REDACTED]"
        assert result[0]["phone"] == "[REDACTED]"
        assert result[0]["ssn"] == "[REDACTED]"
        assert result[0]["credit_card"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_detection_no_false_positives(self, mock_presidio):
        """Test that legitimate data is not flagged as PII."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Test data that should not be flagged as PII
        test_data = [
            {
                "id": 1,
                "company": "Tech Corp",
                "website": "https://techcorp.com",
                "product": "Data Processor",
                "version": "1.0",
                "tenant_id": "test_tenant_001",
            }
        ]

        with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
             patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

            mock_analyzer.analyze.return_value = []  # No PII detected
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "unchanged"

            result = await apply_pii_redaction(test_data)

        # Verify no redaction occurred
        assert result[0]["company"] == "Tech Corp"
        assert result[0]["website"] == "https://techcorp.com"
        assert result[0]["product"] == "Data Processor"
        assert result[0]["version"] == "1.0"


class TestPIIConfiguration:
    """Test PII redaction configuration and settings."""

    @pytest.mark.asyncio
    async def test_pii_redaction_enabled_config(self):
        """Test PII redaction configuration when enabled."""
        # Mock settings to enable PII redaction
        original_enable_pii = settings.ENABLE_PII_REDACTION
        settings.ENABLE_PII_REDACTION = True

        try:
            # Test that PII redaction works when enabled
            sample_data = [
                {
                    "id": 1,
                    "name": "John Doe",
                    "email": "john@example.com",
                    "tenant_id": "test_tenant_001",
                }
            ]

            with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
                 patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

                mock_analyzer = Mock()
                mock_anonymizer = Mock()
                mock_analyzer_class.return_value = mock_analyzer
                mock_anonymizer_class.return_value = mock_anonymizer

                mock_analyzer.analyze.return_value = [
                    Mock(type="PERSON", text="John Doe"),
                    Mock(type="EMAIL_ADDRESS", text="john@example.com"),
                ]
                mock_anonymizer.anonymize.return_value = Mock()
                mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

                result = await apply_pii_redaction(sample_data)

                # Verify PII was redacted
                assert result[0]["name"] == "[REDACTED]"
                assert result[0]["email"] == "[REDACTED]"

        finally:
            # Restore original setting
            settings.ENABLE_PII_REDACTION = original_enable_pii

    @pytest.mark.asyncio
    async def test_pii_redaction_disabled_config(self):
        """Test that data passes through unchanged when PII redaction is disabled."""
        # Mock settings to disable PII redaction
        original_enable_pii = settings.ENABLE_PII_REDACTION
        settings.ENABLE_PII_REDACTION = False

        try:
            # Test data
            sample_data = [
                {
                    "id": 1,
                    "name": "John Doe",
                    "email": "john@example.com",
                    "tenant_id": "test_tenant_001",
                }
            ]

            # Call PII redaction (should return data unchanged)
            result = await apply_pii_redaction(sample_data)

            # Verify data is unchanged
            assert result[0]["name"] == "John Doe"
            assert result[0]["email"] == "john@example.com"

        finally:
            # Restore original setting
            settings.ENABLE_PII_REDACTION = original_enable_pii

    @pytest.mark.asyncio
    async def test_pii_redaction_language_support(self, mock_presidio):
        """Test PII redaction with different languages."""
        mock_analyzer, mock_anonymizer = mock_presidio

        # Test data with different languages
        test_cases = [
            ("en", "John Doe", "john@example.com"),
            ("es", "Juan Pérez", "juan@ejemplo.com"),
            ("fr", "Jean Dupont", "jean@exemple.fr"),
        ]

        for language, name, email in test_cases:
            sample_data = [
                {
                    "id": 1,
                    "name": name,
                    "email": email,
                    "tenant_id": "test_tenant_001",
                }
            ]

            with patch('presidio_analyzer.AnalyzerEngine', return_value=mock_analyzer), \
                 patch('presidio_anonymizer.AnonymizerEngine', return_value=mock_anonymizer):

                mock_analyzer.analyze.return_value = [
                    Mock(type="PERSON", text=name),
                    Mock(type="EMAIL_ADDRESS", text=email),
                ]
                mock_anonymizer.anonymize.return_value = Mock()
                mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

                result = await apply_pii_redaction(sample_data)

            # Verify PII was redacted regardless of language
            assert result[0]["name"] == "[REDACTED]"
            assert result[0]["email"] == "[REDACTED]"


class TestPIIPipelineIntegration:
    """Test PII redaction integration with data processing pipeline."""

    @pytest.mark.asyncio
    async def test_pii_redaction_with_dlt_pipeline(self):
        """Test PII redaction integration with dlt pipeline."""
        from unittest.mock import patch

        # Sample data with PII
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
                "created_at": "2023-12-20T12:00:00Z",
            }
        ]

        # Mock dlt pipeline
        with patch('dlt.pipeline') as mock_pipeline_class:
            mock_pipeline = Mock()
            mock_pipeline_class.return_value = mock_pipeline

            # Mock pipeline execution
            mock_pipeline.run.return_value = Mock()

            # Mock Presidio
            with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
                 patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

                mock_analyzer = Mock()
                mock_anonymizer = Mock()
                mock_analyzer_class.return_value = mock_analyzer
                mock_anonymizer_class.return_value = mock_anonymizer

                mock_analyzer.analyze.return_value = [
                    Mock(type="PERSON", text="John Doe"),
                    Mock(type="EMAIL_ADDRESS", text="john@example.com"),
                    Mock(type="PHONE_NUMBER", text="555-1234"),
                ]
                mock_anonymizer.anonymize.return_value = Mock()
                mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

                # Call PII redaction
                result = await apply_pii_redaction(sample_data)

                # Verify pipeline integration works
                assert len(result) == 1
                assert result[0]["name"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_redaction_error_handling_pipeline(self):
        """Test PII redaction error handling in pipeline context."""
        # Test data that will cause an error
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock Presidio to raise an error
        with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
             patch('presidio_anonymizer.AnonymizerEngine'):

            mock_analyzer = Mock()
            mock_analyzer_class.return_value = mock_analyzer
            mock_analyzer.analyze.side_effect = Exception("Presidio processing error")

            # Call PII redaction (should handle error gracefully)
            result = await apply_pii_redaction(sample_data)

            # Verify data is returned unchanged
            assert result[0]["name"] == "John Doe"
            assert result[0]["email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_pii_redaction_batch_processing(self):
        """Test PII redaction with batch processing."""
        # Large batch of data
        sample_data = []
        for i in range(100):
            sample_data.append({
                "id": i + 1,
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "tenant_id": "test_tenant_001",
            })

        with patch('presidio_analyzer.AnalyzerEngine') as mock_analyzer_class, \
             patch('presidio_anonymizer.AnonymizerEngine') as mock_anonymizer_class:

            mock_analyzer = Mock()
            mock_anonymizer = Mock()
            mock_analyzer_class.return_value = mock_analyzer
            mock_anonymizer_class.return_value = mock_anonymizer

            # Configure analyzer to return PII for all names
            mock_analyzer.analyze.return_value = [
                Mock(type="PERSON", text=f"User {i}")
                for i in range(100)
            ]

            # Configure anonymizer
            mock_anonymizer.anonymize.return_value = Mock()
            mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

            # Process large batch
            result = await apply_pii_redaction(sample_data)

            # Verify all records were processed
            assert len(result) == 100

            # Verify all names were redacted
            for record in result:
                assert record["name"] == "[REDACTED]"

            # Verify analyzer was called for each record
            assert mock_analyzer.analyze.call_count == 100