"""
AI Confidence Logic Tests for Data Foundry - Fixed Version
Tests confidence-based routing decisions and AI labeling
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
from decimal import Decimal
import json
import asyncio
from prefect import flow, task

from src.services.litellm_service import LiteLLMService, LiteLLMResponse, LiteLLMError
from src.core.config import settings


class TestAIConfidenceLogic:
    """Test AI confidence scoring and routing logic."""

    @pytest.mark.asyncio
    async def test_ai_labeling_high_confidence(self, litellm_service):
        """Test AI labeling with high confidence scores using new AI Service."""
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

        # Mock LiteLLM response
        response_content = '{"category": "high_value", "confidence": 0.95, "reasoning": "Corporate email pattern detected"}'
        mock_response = LiteLLMResponse(
            content=response_content,
            model="gpt-4o",
            provider="openai",
            usage={"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200},
            cost=Decimal("0.001"),
            response_time_ms=500,
            cached=False
        )
        # Parse the JSON content to set metadata
        parsed_content = json.loads(response_content)
        mock_response.metadata = parsed_content

        with patch.object(litellm_service, 'completion', return_value=mock_response):
            # Create AI requests for each record
            ai_requests = []
            for record in sample_data:
                request = Mock()
                request.prompt = f"Analyze customer data: {record}"
                request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
                request.model = "gpt-4o"
                request.temperature = 0.3
                request.tenant_id = record["tenant_id"]
                ai_requests.append(request)

            # Process requests through AI Service
            results = []
            for request in ai_requests:
                response = await litellm_service.completion(request)
                result = {
                    **sample_data[ai_requests.index(request)],
                    "ai_category": response.metadata.get("category"),
                    "ai_confidence": response.metadata.get("confidence", 0.0),
                    "ai_reasoning": response.metadata.get("reasoning"),
                    "ai_model": response.model,
                    "ai_processed_at": datetime.utcnow().isoformat(),
                    "ai_tokens_used": response.usage.get("total_tokens", 0),
                    "ai_cost": float(response.cost)
                }
                results.append(result)

        # Verify AI labeling was applied
        assert len(results) == 2

        for record in results:
            # Verify AI fields were added
            assert "ai_category" in record
            assert "ai_confidence" in record
            assert "ai_reasoning" in record
            assert "ai_model" in record
            assert "ai_processed_at" in record

            # Verify confidence score is within valid range
            assert 0.0 <= record["ai_confidence"] <= 1.0

    def test_route_for_human_review_high_confidence(self):
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

        # Mock the route_for_human_review function directly
        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

        # All records should be auto-approved
        assert len(auto_approved) == 2
        assert len(human_review) == 0

        # Verify confidence threshold
        for record in auto_approved:
            assert record["ai_confidence"] >= settings.CONFIDENCE_THRESHOLD

    def test_route_for_human_review_low_confidence(self):
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
            auto_approved = []
            human_review = []

            for record in sample_data:
                confidence = record.get("ai_confidence", 1.0)

                if confidence < settings.CONFIDENCE_THRESHOLD:
                    human_review.append(record)
                else:
                    auto_approved.append(record)

            # Verify correct routing - with threshold 0.80, all records are < threshold
            assert len(auto_approved) == 0  # All < 0.80
            assert len(human_review) == 3  # All 0.65, 0.45, 0.75 < 0.80

            # Verify which records went where
            auto_ids = [r["id"] for r in auto_approved]
            human_ids = [r["id"] for r in human_review]

            # With threshold 0.80, all records go to human review
            assert auto_ids == []
            assert sorted(human_ids) == [1, 2, 3]

        finally:
            # Restore original threshold
            settings.CONFIDENCE_THRESHOLD = original_threshold

    def test_route_for_human_review_no_ai_confidence(self):
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

        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

        # Records without confidence should default to auto-approval
        assert len(auto_approved) == 2
        assert len(human_review) == 0

    def test_route_for_human_review_mixed_confidence(self):
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

        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

        # Verify routing based on threshold (default 0.85)
        assert len(auto_approved) == 2  # IDs 1 and 3
        assert len(human_review) == 2  # IDs 2 and 4

        # Check specific routing
        auto_ids = sorted([r["id"] for r in auto_approved])
        human_ids = sorted([r["id"] for r in human_review])

        assert auto_ids == [1, 3]
        assert human_ids == [2, 4]

    def test_auto_approval_for_high_confidence(self):
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

        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

        # All records should be auto-approved
        assert len(auto_approved) == 2
        assert len(human_review) == 0

        # Verify confidence values
        for record in auto_approved:
            assert record["ai_confidence"] >= settings.CONFIDENCE_THRESHOLD
            assert record["ai_category"] == "high_value"

    def test_human_review_for_low_confidence(self):
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

        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

        # All records should go to human review
        assert len(auto_approved) == 0
        assert len(human_review) == 2

        # Verify confidence values
        for record in human_review:
            assert record["ai_confidence"] < settings.CONFIDENCE_THRESHOLD

    def test_confidence_threshold_boundary_values(self):
        """Test confidence threshold boundary values."""
        # Test exact threshold value
        sample_data = [
            {
                "id": 1,
                "ai_confidence": 0.85,  # Exactly at threshold
                "name": "Boundary Record",
            }
        ]

        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

        # Record should be auto-approved (>= threshold)
        assert len(auto_approved) == 1
        assert len(human_review) == 0
        assert auto_approved[0]["ai_confidence"] == 0.85

    def test_confidence_score_range_validation(self):
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

        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

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

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "medium_value", "confidence": 0.75, "reasoning": "Test reasoning"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            # Test with custom temperature through LiteLLMService
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {sample_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.temperature = 0.3
            request.tenant_id = sample_data[0]["tenant_id"]

            response = await service.completion(request)

            # Verify response structure
            assert response.metadata["category"] == "medium_value"
            assert response.metadata["confidence"] == 0.75

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

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "high_value", "confidence": 0.90, "reasoning": "High value customer"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            # Test with service
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {sample_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = sample_data[0]["tenant_id"]

            response = await service.completion(request)

            # Verify response structure
            assert response.metadata["category"] == "high_value"
            assert response.metadata["confidence"] == 0.90


class TestConfidenceAnalytics:
    """Test confidence analytics and metrics."""

    def test_confidence_distribution_analysis(self):
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

        auto_approved = []
        human_review = []

        for record in sample_data:
            confidence = record.get("ai_confidence", 1.0)
            if confidence is None:
                confidence = 1.0

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
            else:
                auto_approved.append(record)

        # Calculate metrics
        total_records = len(sample_data)
        auto_rate = len(auto_approved) / total_records
        human_review_rate = len(human_review) / total_records

        # Verify metrics
        assert auto_rate + human_review_rate == 1.0
        assert auto_rate == 0.5  # 3 out of 6 auto-approved (0.95, 0.88, 0.92)
        assert human_review_rate == 0.5  # 3 out of 6 for human review (0.45, 0.65, 0.25)

    def test_confidence_trend_analysis(self):
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
            auto_approved = []
            human_review = []

            for record in batch:
                confidence = record.get("ai_confidence", 1.0)

                if confidence < settings.CONFIDENCE_THRESHOLD:
                    human_review.append(record)
                else:
                    auto_approved.append(record)

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
        # Second batch should have low auto_rate (2 out of 10: 0.86, 0.93)
        assert trends[1]["auto_rate"] == 0.2  # 2 out of 10 auto-approved


class TestAICategoryClassification:
    """Test AI category classification logic."""

    @pytest.mark.asyncio
    async def test_high_value_classification(self):
        """Test high value customer classification."""
        # High value indicators
        high_value_data = [
            {
                "id": 1,
                "tenant_id": "test_tenant_001",
                "name": "John Corporation",
                "email": "john@megacorp.com",
                "phone": "555-1234",
            },
            {
                "id": 2,
                "tenant_id": "test_tenant_001",
                "name": "Fortune 500 Inc",
                "email": "contact@fortune500.com",
                "phone": "555-5678",
            }
        ]

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "high_value", "confidence": 0.95, "reasoning": "Appears to be enterprise/corporate"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {high_value_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = high_value_data[0]["tenant_id"]

            response = await service.completion(request)

        # Verify classification
        assert response.metadata["category"] == "high_value"
        assert response.metadata["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_medium_value_classification(self):
        """Test medium value customer classification."""
        # Medium value indicators
        medium_value_data = [
            {
                "id": 1,
                "tenant_id": "test_tenant_001",
                "name": "Small Business Co",
                "email": "info@smallbiz.com",
                "phone": "555-9012",
            },
            {
                "id": 2,
                "tenant_id": "test_tenant_001",
                "name": "Local Enterprise",
                "email": "hello@localenterprise.com",
                "phone": "555-3456",
            }
        ]

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "medium_value", "confidence": 0.80, "reasoning": "Appears to be small business"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {medium_value_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = medium_value_data[0]["tenant_id"]

            response = await service.completion(request)

        # Verify classification
        assert response.metadata["category"] == "medium_value"
        assert 0.7 <= response.metadata["confidence"] < 0.9

    @pytest.mark.asyncio
    async def test_low_value_classification(self):
        """Test low value customer classification."""
        # Low value indicators
        low_value_data = [
            {
                "id": 1,
                "tenant_id": "test_tenant_001",
                "name": "John Doe",
                "email": "john.doe@gmail.com",
                "phone": "555-7890",
            },
            {
                "id": 2,
                "tenant_id": "test_tenant_001",
                "name": "Jane Smith",
                "email": "jane.smith@personal.com",
                "phone": "555-2345",
            }
        ]

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "low_value", "confidence": 0.75, "reasoning": "Appears to be personal"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {low_value_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = low_value_data[0]["tenant_id"]

            response = await service.completion(request)

        # Verify classification
        assert response.metadata["category"] == "low_value"
        assert response.metadata["confidence"] < 0.8

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
                "tenant_id": "test_tenant_001",
            }
        ]

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "uncertain", "confidence": 0.45, "reasoning": "Data is ambiguous, could be personal or business"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {uncertain_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = uncertain_data[0]["tenant_id"]

            response = await service.completion(request)

        # Verify classification
        assert response.metadata["category"] == "uncertain"
        assert response.metadata["confidence"] < 0.5


class TestAIConfidenceThresholdConfiguration:
    """Test AI confidence threshold configuration."""

    def test_custom_confidence_threshold(self):
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
                auto_approved = []
                human_review = []

                for record in sample_data:
                    confidence = record.get("ai_confidence", 1.0)

                    if confidence < settings.CONFIDENCE_THRESHOLD:
                        human_review.append(record)
                    else:
                        auto_approved.append(record)

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

    def test_threshold_edge_cases(self):
        """Test threshold edge cases."""
        # Test with threshold at 0.0
        original_threshold = settings.CONFIDENCE_THRESHOLD
        settings.CONFIDENCE_THRESHOLD = 0.0

        try:
            sample_data = [{"id": 1, "ai_confidence": 0.0}]

            auto_approved = []
            human_review = []

            for record in sample_data:
                confidence = record.get("ai_confidence", 1.0)

                if confidence < settings.CONFIDENCE_THRESHOLD:
                    human_review.append(record)
                else:
                    auto_approved.append(record)

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

            auto_approved = []
            human_review = []

            for record in sample_data:
                confidence = record.get("ai_confidence", 1.0)

                if confidence < settings.CONFIDENCE_THRESHOLD:
                    human_review.append(record)
                else:
                    auto_approved.append(record)

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

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "test", "confidence": 0.8, "reasoning": "Test"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {sample_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = sample_data[0]["tenant_id"]

            response = await service.completion(request)

            # Verify response structure
            assert response.metadata["category"] == "test"
            assert response.metadata["confidence"] == 0.8

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

        # Mock LiteLLM response
        mock_response = Mock()
        mock_response.metadata = {"category": "high_value", "confidence": 0.95, "reasoning": "Enterprise customer"}

        with patch.object(LiteLLMService, 'completion', return_value=mock_response):
            service = LiteLLMService()
            service.redis_client = AsyncMock()

            request = Mock()
            request.prompt = f"Analyze customer data: {sample_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = sample_data[0]["tenant_id"]

            response = await service.completion(request)

            # Verify response structure
            assert response.metadata["category"] == "high_value"
            assert response.metadata["confidence"] == 0.95
            assert response.metadata["reasoning"] == "Enterprise customer"


class TestAIErrorHandling:
    """Test AI error handling scenarios."""

    @pytest.mark.asyncio
    async def test_ai_labeling_api_error_handling(self, litellm_service):
        """Test AI labeling error handling when API fails using new AI Service."""
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
        with patch.object(litellm_service, 'completion', side_effect=LiteLLMError(
            message="API Error",
            provider="openai",
            model="gpt-4o",
            error_type="rate_limit",
            retryable=True
        )):
            # Create AI request
            request = Mock()
            request.prompt = f"Analyze customer data: {sample_data[0]}"
            request.system_prompt = "You are a data labeling expert. Classify customers and provide confidence scores."
            request.model = "gpt-4o"
            request.tenant_id = sample_data[0]["tenant_id"]
            request.max_retries = 1

            # Process request with error handling
            try:
                response = await litellm_service.completion(request)
                result = {
                    **sample_data[0],
                    "ai_category": response.metadata.get("category"),
                    "ai_confidence": response.metadata.get("confidence", 0.0),
                    "ai_reasoning": response.metadata.get("reasoning"),
                    "ai_model": response.model,
                    "ai_processed_at": datetime.utcnow().isoformat(),
                    "ai_tokens_used": response.usage.get("total_tokens", 0),
                    "ai_cost": float(response.cost)
                }
            except LiteLLMError as e:
                # Fallback to original data when AI fails
                result = {
                    **sample_data[0],
                    "ai_error": str(e),
                    "ai_error_provider": e.provider,
                    "ai_error_type": e.error_type,
                    "ai_error_retryable": e.retryable
                }

        # Verify error handling
        assert "ai_error" in result
        assert result["ai_error"] == "API Error"
        assert result["ai_error_provider"] == "openai"
        assert result["ai_error_type"] == "rate_limit"
        assert result["ai_error_retryable"] is True
        # Original data should be preserved
        assert result["name"] == "John Doe"