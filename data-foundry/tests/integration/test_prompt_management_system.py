"""
Integration Tests for Prompt Management System

These tests verify the end-to-end functionality of the complete Prompt Management System,
including system prompts, templates, validation, and the PromptManager.
"""

import pytest
from pathlib import Path
from typing import Dict, Any

from src.core.prompts import (
    PromptManager,
    get_prompt_manager,
    SystemPromptType,
    load_template,
    render_template,
    validate_template_syntax,
)
from src.core.prompts.prompt_manager import PromptManagerError, reset_prompt_manager


class TestPromptManagementIntegration:
    """Integration tests for the complete prompt management system."""

    @pytest.fixture(autouse=True)
    def reset_global_manager(self):
        """Reset global prompt manager before each test."""
        reset_prompt_manager()
        yield
        reset_prompt_manager()

    def test_end_to_end_workflow(self):
        """Test complete workflow from system prompts to template rendering."""
        # 1. Get system prompt
        manager = get_prompt_manager()
        system_prompt = manager.get_system_prompt("data_labeling_expert")
        assert "data classification" in system_prompt.lower()

        # 2. Load user template
        template = manager.get_template("data_classification.yaml")
        assert "metadata" in template
        assert "template" in template

        # 3. Render template with data
        variables = {
            "data_record": {
                "name": "Acme Corp",
                "email": "contact@acme.com",
                "revenue": "1000000"
            },
            "categories": ["enterprise", "high_value", "prospect"],
            "context": "Lead qualification for sales team"
        }

        rendered = manager.render_template("data_classification.yaml", variables)
        assert "Acme Corp" in rendered
        assert "contact@acme.com" in rendered
        assert "enterprise" in rendered

    def test_system_prompts_integration(self):
        """Test system prompts integration with different types."""
        manager = get_prompt_manager()

        # Test all system prompt types
        prompt_types = manager.list_system_prompts()
        assert len(prompt_types) == 3

        for prompt_type in prompt_types:
            prompt = manager.get_system_prompt(prompt_type)
            assert isinstance(prompt, str)
            assert len(prompt) > 100  # Prompts should be substantial

        # Verify specific content
        pii_prompt = manager.get_system_prompt("pii_analyst")
        assert "privacy" in pii_prompt.lower()

        confidence_prompt = manager.get_system_prompt("confidence_assessor")
        assert "scoring" in confidence_prompt.lower()

    def test_template_validation_integration(self):
        """Test template validation in the integrated system."""
        manager = get_prompt_manager()

        # Valid template should pass
        assert manager.validate_template("data_classification.yaml") is True

        # Get template metadata
        metadata = manager.get_template_metadata("data_classification.yaml")
        assert metadata["name"] == "Data Classification Template"
        assert metadata["version"] == "1.0.0"
        assert metadata["type"] == "data_classification"

    def test_caching_integration(self):
        """Test caching behavior across the system."""
        manager = get_prompt_manager()

        # First load - should cache
        template1 = manager.get_template("data_classification.yaml")
        assert len(manager._template_cache) > 0

        # Second load - should use cache
        template2 = manager.get_template("data_classification.yaml")
        assert template1 is template2

        # System prompts should also cache
        prompt1 = manager.get_system_prompt("data_labeling_expert")
        assert len(manager._system_prompts_cache) > 0

        prompt2 = manager.get_system_prompt("data_labeling_expert")
        assert prompt1 is prompt2

    def test_error_handling_integration(self):
        """Test error handling across the integrated system."""
        manager = get_prompt_manager()

        # Invalid system prompt
        with pytest.raises(PromptManagerError):
            manager.get_system_prompt("invalid_type")

        # Invalid template
        with pytest.raises(PromptManagerError):
            manager.get_template("nonexistent.yaml")

        # Template rendering with missing variables
        with pytest.raises(PromptManagerError, match="Missing required"):
            manager.render_template("data_classification.yaml", {})

    def test_concurrent_access_integration(self):
        """Test thread-safe concurrent access."""
        import threading
        import time

        manager = get_prompt_manager()
        results = []
        errors = []

        def worker():
            try:
                # Each thread performs various operations
                prompt = manager.get_system_prompt("data_labeling_expert")
                template = manager.get_template("data_classification.yaml")
                variables = {"data_record": {"test": "data"}, "categories": ["test"], "context": "test"}
                rendered = manager.render_template("data_classification.yaml", variables)
                results.append((prompt, template, rendered))
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5
        assert all(r[0] is not None and r[1] is not None and r[2] is not None for r in results)

    def test_template_rendering_with_complex_data(self):
        """Test template rendering with complex nested data."""
        manager = get_prompt_manager()

        complex_variables = {
            "data_record": {
                "company": {
                    "name": "Tech Solutions Inc",
                    "address": {
                        "street": "123 Tech Street",
                        "city": "San Francisco",
                        "state": "CA",
                        "zip": "94105"
                    },
                    "contacts": [
                        {"name": "John Doe", "email": "john@techsolutions.com", "role": "CEO"},
                        {"name": "Jane Smith", "email": "jane@techsolutions.com", "role": "CTO"}
                    ]
                },
                "metrics": {
                    "employees": 150,
                    "revenue": 5000000,
                    "growth_rate": 0.25
                }
            },
            "categories": ["enterprise", "tech", "growth_stage"],
            "context": "B2B SaaS company evaluation",
            "examples": [
                {
                    "input": {"company": {"name": "SimilarCorp"}},
                    "category": "enterprise",
                    "reasoning": "Similar company profile"
                }
            ],
            "rules": [
                "Consider company size",
                "Evaluate growth potential",
                "Assess market fit"
            ],
            "threshold": 0.85
        }

        rendered = manager.render_template("data_classification.yaml", complex_variables)

        # Verify all data was rendered
        assert "Tech Solutions Inc" in rendered
        assert "123 Tech Street" in rendered
        assert "John Doe" in rendered
        assert "150" in rendered
        assert "5000000" in rendered
        assert "enterprise" in rendered
        assert "SimilarCorp" in rendered
        assert "Consider company size" in rendered

    def test_system_prompt_consistency(self):
        """Test that system prompts remain consistent across accesses."""
        manager = get_prompt_manager()

        # Get prompt multiple times
        prompt1 = manager.get_system_prompt("data_labeling_expert")
        prompt2 = manager.get_system_prompt("data_labeling_expert")
        prompt3 = manager.get_system_prompt("data_labeling_expert")

        # Should all be identical
        assert prompt1 == prompt2 == prompt3

        # Even after clearing cache
        manager.clear_cache()
        prompt4 = manager.get_system_prompt("data_labeling_expert")
        assert prompt1 == prompt4

    def test_template_metadata_versioning(self):
        """Test template metadata versioning."""
        manager = get_prompt_manager()

        metadata = manager.get_template_metadata("data_classification.yaml")
        version = metadata["version"]

        # Should follow semantic versioning
        assert isinstance(version, str)
        parts = version.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_response_format_validation(self):
        """Test response format validation in templates."""
        manager = get_prompt_manager()
        template = manager.get_template("data_classification.yaml")

        response_format = template["response_format"]

        # Should be a valid JSON schema
        assert response_format["type"] == "object"
        assert "properties" in response_format
        assert "required" in response_format

        # Check required fields
        required_fields = response_format["required"]
        assert "category" in required_fields
        assert "confidence" in required_fields
        assert "reasoning" in required_fields

        # Check property types
        properties = response_format["properties"]
        assert properties["category"]["type"] == "string"
        assert properties["confidence"]["type"] == "number"

    def test_integration_with_ai_workflow(self):
        """Simulate complete AI workflow using prompt management."""
        manager = get_prompt_manager()

        # 1. Prepare data
        data_record = {
            "name": "Global Manufacturing Co",
            "email": "info@globalmfg.com",
            "industry": "Manufacturing",
            "employees": 5000
        }

        # 2. Get system prompts for different AI roles
        data_labeling_prompt = manager.get_system_prompt("data_labeling_expert")
        pii_prompt = manager.get_system_prompt("pii_analyst")
        confidence_prompt = manager.get_system_prompt("confidence_assessor")

        # 3. Prepare user prompt template
        variables = {
            "data_record": data_record,
            "categories": ["enterprise", "manufacturing", "global"],
            "context": "Company classification for CRM system"
        }

        user_prompt = manager.render_template("data_classification.yaml", variables)

        # 4. Verify all components are ready for AI processing
        assert len(data_labeling_prompt) > 500
        assert len(pii_prompt) > 500
        assert len(confidence_prompt) > 500
        assert len(user_prompt) > 100
        assert "Global Manufacturing Co" in user_prompt
        assert "manufacturing" in user_prompt.lower()

    def test_template_consistency_checks(self):
        """Test template consistency warnings and checks."""
        from src.core.prompts.validation import validate_template_consistency

        manager = get_prompt_manager()
        template = manager.get_template("data_classification.yaml")

        # Check for consistency issues
        warnings = validate_template_consistency(template)

        # Warnings should be list (may be empty)
        assert isinstance(warnings, list)

        # Log any warnings for review
        if warnings:
            print(f"Template consistency warnings: {warnings}")

    def test_performance_with_multiple_operations(self):
        """Test performance with multiple rapid operations."""
        import time

        manager = get_prompt_manager()

        # Perform multiple operations rapidly
        start_time = time.time()

        for i in range(10):
            # Mix of different operations
            manager.get_system_prompt("data_labeling_expert")
            manager.get_template("data_classification.yaml")
            variables = {
                "data_record": {"id": i, "value": f"test_{i}"},
                "categories": ["test"],
                "context": f"Test iteration {i}"
            }
            manager.render_template("data_classification.yaml", variables)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete quickly (under 1 second)
        assert duration < 1.0, f"Operations took too long: {duration}s"

    def test_fallback_behavior(self):
        """Test fallback behavior when templates are unavailable."""
        # This test would be relevant when implementing fallback templates
        manager = get_prompt_manager()

        # Current behavior: raises error
        with pytest.raises(PromptManagerError):
            manager.get_template("nonexistent_template.yaml")

        # In a production system, this could trigger fallback logic