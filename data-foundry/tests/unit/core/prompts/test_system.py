"""
Tests for System Prompts module - Following TDD approach
These tests will fail initially and drive the implementation of the System Prompts module.
"""

import pytest
from typing import Dict, Any

from src.core.prompts.system import (
    get_system_prompt,
    get_all_system_prompts,
    SystemPromptType,
    DataLabelingExpert,
    PIIAnalyst,
    ConfidenceAssessor,
)


class TestSystemPrompts:
    """Test cases for the System Prompts module."""

    def test_get_system_prompt_data_labeling_expert(self):
        """Test retrieving DataLabelingExpert system prompt."""
        prompt = get_system_prompt(SystemPromptType.DATA_LABELING_EXPERT)

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "data classification" in prompt.lower()
        assert "labeling" in prompt.lower()
        assert "expert" in prompt.lower()

    def test_get_system_prompt_pii_analyst(self):
        """Test retrieving PIIAnalyst system prompt."""
        prompt = get_system_prompt(SystemPromptType.PII_ANALYST)

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "pii" in prompt.lower()
        assert "privacy" in prompt.lower()
        assert "detection" in prompt.lower()

    def test_get_system_prompt_confidence_assessor(self):
        """Test retrieving ConfidenceAssessor system prompt."""
        prompt = get_system_prompt(SystemPromptType.CONFIDENCE_ASSESSOR)

        assert prompt is not None
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "confidence" in prompt.lower()
        assert "assessment" in prompt.lower()
        assert "scoring" in prompt.lower()

    def test_get_system_prompt_invalid_type(self):
        """Test that invalid prompt type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid system prompt type"):
            get_system_prompt("invalid_prompt_type")  # type: ignore

    def test_get_all_system_prompts(self):
        """Test retrieving all system prompts."""
        prompts = get_all_system_prompts()

        assert isinstance(prompts, dict)
        assert len(prompts) == 3  # We expect exactly 3 system prompts

        expected_types = [
            SystemPromptType.DATA_LABELING_EXPERT,
            SystemPromptType.PII_ANALYST,
            SystemPromptType.CONFIDENCE_ASSESSOR,
        ]

        for prompt_type in expected_types:
            assert prompt_type in prompts
            assert isinstance(prompts[prompt_type], str)
            assert len(prompts[prompt_type]) > 0

    def test_data_labeling_expert_prompt_content(self):
        """Test DataLabelingExpert prompt has required content."""
        prompt = get_system_prompt(SystemPromptType.DATA_LABELING_EXPERT)

        # Check for key concepts in data labeling
        required_concepts = [
            "classification",
            "categorization",
            "data quality",
            "consistency",
            "accuracy",
        ]

        for concept in required_concepts:
            assert concept in prompt.lower()

    def test_pii_analyst_prompt_content(self):
        """Test PIIAnalyst prompt has required content."""
        prompt = get_system_prompt(SystemPromptType.PII_ANALYST)

        # Check for key PII concepts
        required_concepts = [
            "personal information",
            "sensitive data",
            "gdpr",
            "privacy",
            "identification",
        ]

        for concept in required_concepts:
            assert concept in prompt.lower()

    def test_confidence_assessor_prompt_content(self):
        """Test ConfidenceAssessor prompt has required content."""
        prompt = get_system_prompt(SystemPromptType.CONFIDENCE_ASSESSOR)

        # Check for key confidence assessment concepts
        required_concepts = [
            "confidence score",
            "uncertainty",
            "probability",
            "threshold",
            "reliability",
        ]

        for concept in required_concepts:
            assert concept in prompt.lower()

    def test_system_prompt_constants_exist(self):
        """Test that system prompt constants are properly defined."""
        # Test that the constants exist and are strings
        assert isinstance(DataLabelingExpert.PROMPT, str)
        assert len(DataLabelingExpert.PROMPT) > 0

        assert isinstance(PIIAnalyst.PROMPT, str)
        assert len(PIIAnalyst.PROMPT) > 0

        assert isinstance(ConfidenceAssessor.PROMPT, str)
        assert len(ConfidenceAssessor.PROMPT) > 0

    def test_system_prompt_descriptions(self):
        """Test that system prompts have descriptions."""
        assert hasattr(DataLabelingExpert, 'DESCRIPTION')
        assert isinstance(DataLabelingExpert.DESCRIPTION, str)
        assert len(DataLabelingExpert.DESCRIPTION) > 0

        assert hasattr(PIIAnalyst, 'DESCRIPTION')
        assert isinstance(PIIAnalyst.DESCRIPTION, str)
        assert len(PIIAnalyst.DESCRIPTION) > 0

        assert hasattr(ConfidenceAssessor, 'DESCRIPTION')
        assert isinstance(ConfidenceAssessor.DESCRIPTION, str)
        assert len(ConfidenceAssessor.DESCRIPTION) > 0

    def test_system_prompt_versions(self):
        """Test that system prompts have version information."""
        assert hasattr(DataLabelingExpert, 'VERSION')
        assert isinstance(DataLabelingExpert.VERSION, str)

        assert hasattr(PIIAnalyst, 'VERSION')
        assert isinstance(PIIAnalyst.VERSION, str)

        assert hasattr(ConfidenceAssessor, 'VERSION')
        assert isinstance(ConfidenceAssessor.VERSION, str)


class TestSystemPromptType:
    """Test cases for SystemPromptType enum."""

    def test_system_prompt_type_values(self):
        """Test that SystemPromptType has correct values."""
        assert SystemPromptType.DATA_LABELING_EXPERT == "data_labeling_expert"
        assert SystemPromptType.PII_ANALYST == "pii_analyst"
        assert SystemPromptType.CONFIDENCE_ASSESSOR == "confidence_assessor"

    def test_system_prompt_type_count(self):
        """Test that we have exactly 3 system prompt types."""
        assert len(SystemPromptType) == 3