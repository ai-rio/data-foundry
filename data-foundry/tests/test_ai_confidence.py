"""
AI Confidence Logic Tests for Data Foundry
Tests confidence-based routing decisions and AI labeling
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.tasks.ingestion import apply_ai_labeling, route_for_human_review
from src.core.config import settings


class TestAIConfidenceLogic:
    """Test AI confidence scoring and routing logic."""

    @pytest.mark.asyncio
    async def test_ai_labeling_high_confidence(self, mock_openai):
        """Test AI labeling with high confidence scores."""
        # Sample data
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@company.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
            },
            {
                "id": 2,
                "name": "Jane Smith",
                "email": "jane@enterprise.org",
                "phone": "555-5678",
                "tenant_id": "test_tenant_001",
            }
        ]

        with patch('openai.OpenAI', return_value=mock_openai):

            result = await apply_ai_labeling(sample_data)

        # Verify AI labeling was applied
        assert len(result) == 2

        for record in result:
            # Verify AI fields were added
            assert "ai_category" in record
            assert "ai_confidence" in record
            assert "ai_reasoning" in record
            assert "ai_model" in record
            assert "ai_processed_at" in record

            # Verify confidence score is within valid range
            assert 0.0 <= record["ai_confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_ai_labeling_low_confidence(self):
        """Test AI labeling with low confidence scores."""
        # Sample data that might result in low confidence
        sample_data = [
            {
                "id": 1,
                "name": "Uncertain User",
                "email": "uncertain@example.com",
                "phone": "555-0000",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock low confidence response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "uncertain", "confidence": 0.45, "reasoning": "Data is ambiguous"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(sample_data)

        # Verify low confidence was recorded
        assert result[0]["ai_confidence"] == 0.45
        assert result[0]["ai_category"] == "uncertain"
        assert "ambiguous" in result[0]["ai_reasoning"].lower()

    @pytest.mark.asyncio
    async def test_ai_labeling_api_error_handling(self):
        """Test AI labeling error handling when API fails."""
        # Sample data
        sample_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock API error
        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.side_effect = Exception("API Error")
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(sample_data)

        # Verify error handling
        assert "ai_error" in result[0]
        assert result[0]["ai_error"] == "API Error"
        # Original data should be preserved
        assert result[0]["name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_route_for_human_review_high_confidence(self):
        """Test routing for human review with high confidence records."""
        # High confidence data
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.95,
                "name": "High Confidence Record",
            },
            {
                "id": 2,
                "ai_confidence": 0.92,
                "name": "Another High Confidence Record",
            }
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # All records should be auto-approved
        assert len(auto_approved) == 2
        assert len(human_review) == 0

        # Verify confidence threshold
        for record in auto_approved:
            assert record["ai_confidence"] >= settings.CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_route_for_human_review_low_confidence(self):
        """Test routing for human review with low confidence records."""
        # Low confidence data
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.65,
                "name": "Low Confidence Record 1",
            },
            {
                "id": 2,
                "ai_confidence": 0.45,
                "name": "Low Confidence Record 2",
            },
            {
                "id": 3,
                "ai_confidence": 0.75,
                "name": "Medium Confidence Record",
            }
        ]

        # Mock settings with lower threshold
        original_threshold = settings.CONFIDENCE_THRESHOLD
        settings.CONFIDENCE_THRESHOLD = 0.80

        try:
            auto_approved, human_review = await route_for_human_review(sample_data)

            # Verify correct routing
            assert len(auto_approved) == 1  # Only 0.75 >= 0.80
            assert len(human_review) == 2  # 0.65 and 0.45 < 0.80

            # Verify which records went where
            auto_ids = [r["id"] for r in auto_approved]
            human_ids = [r["id"] for r in human_review]

            assert 3 in auto_ids
            assert 1 in human_ids
            assert 2 in human_ids

        finally:
            # Restore original threshold
            settings.CONFIDENCE_THRESHOLD = original_threshold

    @pytest.mark.asyncio
    async def test_route_for_human_review_no_ai_confidence(self):
        """Test routing when AI confidence is not available."""
        # Data without confidence scores
        sample_data = [
            {
                "id": 1,
                "name": "No Confidence Record",
                # No ai_confidence field
            },
            {
                "id": 2,
                "ai_confidence": None,
                "name": "None Confidence Record",
            }
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # Records without confidence should default to auto-approval
        assert len(auto_approved) == 2
        assert len(human_review) == 0

    @pytest.mark.asyncio
    async def test_route_for_human_review_mixed_confidence(self):
        """Test routing with mixed confidence levels."""
        # Mixed confidence data
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.95,  # High
                "name": "Enterprise Customer",
            },
            {
                "id": 2,
                "ai_confidence": 0.65,  # Low
                "name": "Small Business",
            },
            {
                "id": 3,
                "ai_confidence": 0.88,  # High
                "name": "Corporate Account",
            },
            {
                "id": 4,
                "ai_confidence": 0.25,  # Very low
                "name": "Personal Account",
            }
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # Verify routing based on threshold (default 0.85)
        assert len(auto_approved) == 2  # IDs 1 and 3
        assert len(human_review) == 2  # IDs 2 and 4

        # Check specific routing
        auto_ids = sorted([r["id"] for r in auto_approved])
        human_ids = sorted([r["id"] for r in human_review])

        assert auto_ids == [1, 3]
        assert human_ids == [2, 4]

    @pytest.mark.asyncio
    async def test_auto_approval_for_high_confidence(self):
        """Test that high confidence records are auto-approved."""
        # High confidence records
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.95,
                "ai_category": "high_value",
                "name": "Large Enterprise",
            },
            {
                "id": 2,
                "ai_confidence": 0.98,
                "ai_category": "high_value",
                "name": "Fortune 500 Company",
            }
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # All records should be auto-approved
        assert len(auto_approved) == 2
        assert len(human_review) == 0

        # Verify confidence values
        for record in auto_approved:
            assert record["ai_confidence"] >= settings.CONFIDENCE_THRESHOLD
            assert record["ai_category"] == "high_value"

    @pytest.mark.asyncio
    async def test_human_review_for_low_confidence(self):
        """Test that low confidence records go to human review."""
        # Low confidence records
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.45,
                "ai_category": "uncertain",
                "name": "Ambiguous Record",
            },
            {
                "id": 2,
                "ai_confidence": 0.65,
                "ai_category": "medium_value",
                "name": "Questionable Classification",
            }
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # All records should go to human review
        assert len(auto_approved) == 0
        assert len(human_review) == 2

        # Verify confidence values
        for record in human_review:
            assert record["ai_confidence"] < settings.CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_confidence_threshold_boundary_values(self):
        """Test confidence threshold boundary values."""
        # Test exact threshold value
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.85,  # Exactly at threshold
                "name": "Boundary Record",
            }
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # Record should be auto-approved (>= threshold)
        assert len(auto_approved) == 1
        assert len(human_review) == 0
        assert auto_approved[0]["ai_confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_confidence_score_range_validation(self):
        """Test that confidence scores are within valid range."""
        # Test data with extreme confidence values
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.0,  # Minimum possible
                "name": "Lowest Confidence",
            },
            {
                "id": 2,
                "ai_confidence": 1.0,  # Maximum possible
                "name": "Highest Confidence",
            },
            {
                "id": 3,
                "ai_confidence": 0.5,  # Middle value
                "name": "Medium Confidence",
            }
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # All confidence values should be preserved
        for record in auto_approved + human_review:
            assert 0.0 <= record["ai_confidence"] <= 1.0


class TestAIModelIntegration:
    """Test AI model integration and configuration."""

    @pytest.mark.asyncio
    async def test_ai_labeling_with_custom_temperature(self):
        """Test AI labeling with custom temperature setting."""
        sample_data = [
            {
                "id": 1,
                "name": "Test User",
                "email": "test@example.com",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "medium_value", "confidence": 0.75, "reasoning": "Test reasoning"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            # Test with custom temperature
            result = await apply_ai_labeling(sample_data)

        # Verify temperature was used
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == settings.OPENAI_TEMPERATURE

    @pytest.mark.asyncio
    async def test_ai_labeling_with_custom_max_tokens(self):
        """Test AI labeling with custom max tokens setting."""
        sample_data = [
            {
                "id": 1,
                "name": "Test User",
                "email": "test@example.com",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "high_value", "confidence": 0.90, "reasoning": "High value customer"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            # Test with custom max tokens
            result = await apply_ai_labeling(sample_data)

        # Verify max tokens was used
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["max_tokens"] == settings.OPENAI_MAX_TOKENS

    @pytest.mark.asyncio
    async def test_ai_labeling_with_different_models(self):
        """Test AI labeling with different AI models."""
        sample_data = [
            {
                "id": 1,
                "name": "Test User",
                "email": "test@example.com",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock different model responses
        test_models = [
            "gpt-4o",
            "gpt-4-turbo",
            "claude-3-opus",
        ]

        for model in test_models:
            with patch('openai.OpenAI') as mock_client_class:
                mock_client = Mock()
                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message.content = '{"category": "test", "confidence": 0.8, "reasoning": "Test"}'
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                # Test with different model
                result = await apply_ai_labeling(sample_data)

                # Verify model was used
                mock_client.chat.completions.create.assert_called_once()
                call_args = mock_client.chat.completions.create.call_args
                assert call_args[1]["model"] == model


class TestConfidenceAnalytics:
    """Test confidence analytics and metrics."""

    @pytest.mark.asyncio
    async def test_confidence_distribution_analysis(self):
        """Test confidence distribution analysis."""
        # Sample data with various confidence scores
        sample_data = [
            {"id": 1, "ai_confidence": 0.95},
            {"id": 2, "ai_confidence": 0.45},
            {"id": 3, "ai_confidence": 0.88},
            {"id": 4, "ai_confidence": 0.65},
            {"id": 5, "ai_confidence": 0.92},
            {"id": 6, "ai_confidence": 0.25},
        ]

        auto_approved, human_review = await route_for_human_review(sample_data)

        # Calculate metrics
        total_records = len(sample_data)
        auto_rate = len(auto_approved) / total_records
        human_review_rate = len(human_review) / total_records

        # Verify metrics
        assert auto_rate + human_review_rate == 1.0
        assert auto_rate == 0.5  # 3 out of 6 auto-approved (0.95, 0.88, 0.92)
        assert human_review_rate == 0.5  # 3 out of 6 for human review (0.45, 0.65, 0.25)

    @pytest.mark.asyncio
    async def test_confidence_trend_analysis(self):
        """Test confidence trend analysis over multiple batches."""
        # Simulate multiple batches of data
        batches = []
        for batch_num in range(5):
            batch = []
            for i in range(10):
                # Simulate varying confidence patterns
                if batch_num == 0:
                    confidence = 0.9 + (i * 0.01)  # High confidence batch
                elif batch_num == 1:
                    confidence = 0.3 + (i * 0.07)  # Low confidence batch
                else:
                    confidence = 0.5 + (i * 0.05)  # Medium confidence batch

                batch.append({
                    "id": batch_num * 10 + i + 1,
                    "ai_confidence": min(confidence, 1.0),
                })
            batches.append(batch)

        # Analyze each batch
        trends = []
        for batch in batches:
            auto_approved, human_review = await route_for_human_review(batch)
            avg_confidence = sum(r["ai_confidence"] for r in batch) / len(batch)
            auto_rate = len(auto_approved) / len(batch)

            trends.append({
                "batch": len(trends) + 1,
                "avg_confidence": avg_confidence,
                "auto_rate": auto_rate,
                "human_review_rate": len(human_review) / len(batch),
            })

        # Verify trends make sense
        assert len(trends) == 5
        # First batch should have highest auto_rate
        assert trends[0]["auto_rate"] == 1.0  # All auto-approved
        # Second batch should have lowest auto_rate
        assert trends[1]["auto_rate"] == 0.0  # All for human review


class TestAICategoryClassification:
    """Test AI category classification logic."""

    @pytest.mark.asyncio
    async def test_high_value_classification(self):
        """Test high value customer classification."""
        # High value indicators
        high_value_data = [
            {
                "id": 1,
                "name": "John Corporation",
                "email": "john@megacorp.com",
                "phone": "555-1234",
            },
            {
                "id": 2,
                "name": "Fortune 500 Inc",
                "email": "contact@fortune500.com",
                "phone": "555-5678",
            }
        ]

        # Mock high confidence response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "Appears to be enterprise/corporate"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(high_value_data)

        # Verify classification
        for record in result:
            assert record["ai_category"] == "high_value"
            assert record["ai_confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_medium_value_classification(self):
        """Test medium value customer classification."""
        # Medium value indicators
        medium_value_data = [
            {
                "id": 1,
                "name": "Small Business Co",
                "email": "info@smallbiz.com",
                "phone": "555-9012",
            },
            {
                "id": 2,
                "name": "Local Enterprise",
                "email": "hello@localenterprise.com",
                "phone": "555-3456",
            }
        ]

        # Mock medium confidence response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "medium_value", "confidence": 0.80, "reasoning": "Appears to be small business"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(medium_value_data)

        # Verify classification
        for record in result:
            assert record["ai_category"] == "medium_value"
            assert 0.7 <= record["ai_confidence"] < 0.9

    @pytest.mark.asyncio
    async def test_low_value_classification(self):
        """Test low value customer classification."""
        # Low value indicators
        low_value_data = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john.doe@gmail.com",
                "phone": "555-7890",
            },
            {
                "id": 2,
                "name": "Jane Smith",
                "email": "jane.smith@personal.com",
                "phone": "555-2345",
            }
        ]

        # Mock low confidence response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "low_value", "confidence": 0.75, "reasoning": "Appears to be personal"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(low_value_data)

        # Verify classification
        for record in result:
            assert record["ai_category"] == "low_value"
            assert record["ai_confidence"] < 0.8

    @pytest.mark.asyncio
    async def test_uncertain_classification(self):
        """Test uncertain classification."""
        # Ambiguous data
        uncertain_data = [
            {
                "id": 1,
                "name": "Maybe Business",
                "email": "contact@maybe.com",
                "phone": "555-5555",
            }
        ]

        # Mock uncertain response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "uncertain", "confidence": 0.45, "reasoning": "Data is ambiguous, could be personal or business"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(uncertain_data)

        # Verify classification
        assert result[0]["ai_category"] == "uncertain"
        assert result[0]["ai_confidence"] < 0.5


class TestAIConfidenceThresholdConfiguration:
    """Test AI confidence threshold configuration."""

    @pytest.mark.asyncio
    async def test_custom_confidence_threshold(self):
        """Test custom confidence threshold settings."""
        # Sample data
        sample_data = [
            {"id": 1, "ai_confidence": 0.90},
            {"id": 2, "ai_confidence": 0.75},
            {"id": 3, "ai_confidence": 0.60},
        ]

        # Test with different thresholds
        test_thresholds = [0.50, 0.75, 0.90]

        for threshold in test_thresholds:
            original_threshold = settings.CONFIDENCE_THRESHOLD
            settings.CONFIDENCE_THRESHOLD = threshold

            try:
                auto_approved, human_review = await route_for_human_review(sample_data)

                # Verify routing based on threshold
                if threshold == 0.50:
                    assert len(auto_approved) == 3  # All >= 0.50
                    assert len(human_review) == 0
                elif threshold == 0.75:
                    assert len(auto_approved) == 2  # IDs 1, 2 >= 0.75
                    assert len(human_review) == 1  # ID 3 < 0.75
                elif threshold == 0.90:
                    assert len(auto_approved) == 1  # ID 1 >= 0.90
                    assert len(human_review) == 2  # IDs 2, 3 < 0.90

            finally:
                settings.CONFIDENCE_THRESHOLD = original_threshold

    @pytest.mark.asyncio
    async def test_threshold_edge_cases(self):
        """Test threshold edge cases."""
        # Test with threshold at 0.0
        original_threshold = settings.CONFIDENCE_THRESHOLD
        settings.CONFIDENCE_THRESHOLD = 0.0

        try:
            sample_data = [{"id": 1, "ai_confidence": 0.0}]
            auto_approved, human_review = await route_for_human_review(sample_data)

            # Even 0.0 confidence should be auto-approved with 0.0 threshold
            assert len(auto_approved) == 1
            assert len(human_review) == 0

        finally:
            settings.CONFIDENCE_THRESHOLD = original_threshold

        # Test with threshold at 1.0
        settings.CONFIDENCE_THRESHOLD = 1.0

        try:
            sample_data = [
                {"id": 1, "ai_confidence": 0.99},
                {"id": 2, "ai_confidence": 1.0},
            ]
            auto_approved, human_review = await route_for_human_review(sample_data)

            # Only exactly 1.0 should be auto-approved
            assert len(auto_approved) == 1
            assert len(human_review) == 1

        finally:
            settings.CONFIDENCE_THRESHOLD = original_threshold


class TestAIPromptEngineering:
    """Test AI prompt engineering and system messages."""

    @pytest.mark.asyncio
    async def test_system_message_configuration(self):
        """Test system message configuration."""
        sample_data = [
            {
                "id": 1,
                "name": "Test User",
                "email": "test@example.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "test", "confidence": 0.8, "reasoning": "Test"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(sample_data)

            # Verify system message was included
            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args[1]["messages"]

            # Check system message
            assert messages[0]["role"] == "system"
            assert "data labeling expert" in messages[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_prompt_structure(self):
        """Test prompt structure and format."""
        sample_data = [
            {
                "id": 1,
                "name": "John Corporation",
                "email": "john@corp.com",
                "phone": "555-1234",
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "Enterprise customer"}'

        with patch('openai.OpenAI') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await apply_ai_labeling(sample_data)

            # Verify prompt structure
            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args[1]["messages"]

            # Check user message contains expected fields
            user_message = messages[1]
            assert user_message["role"] == "user"
            assert "Name: John Corporation" in user_message["content"]
            assert "Email: john@corp.com" in user_message["content"]
            assert "Phone: 555-1234" in user_message["content"]
            assert "categories" in user_message["content"].lower()
            assert "confidence" in user_message["content"].lower()
            assert "return json" in user_message["content"].lower()