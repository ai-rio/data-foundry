"""
Tests for Prompt Templates module - Following TDD approach
These tests will fail initially and drive the implementation of the YAML template system.
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from typing import Dict, Any

from src.core.prompts.templates import (
    load_template,
    render_template,
    get_template_metadata,
    TemplateType,
    DataClassificationTemplate,
)


class TestYAMLTemplates:
    """Test cases for YAML prompt template functionality."""

    def test_load_data_classification_template(self):
        """Test loading the data classification template from YAML."""
        template = load_template("data_classification.yaml")

        assert template is not None
        assert isinstance(template, dict)
        assert "metadata" in template
        assert "template" in template
        assert "response_format" in template

    def test_template_metadata_structure(self):
        """Test that template metadata has required fields."""
        template = load_template("data_classification.yaml")
        metadata = template["metadata"]

        required_fields = [
            "name",
            "version",
            "description",
            "type",
            "author",
            "created_at",
        ]

        for field in required_fields:
            assert field in metadata

    def test_template_has_jinja2_variables(self):
        """Test that template contains Jinja2 variables."""
        template = load_template("data_classification.yaml")
        template_content = template["template"]

        # Check for Jinja2 variable syntax
        assert "{{" in template_content
        assert "}}" in template_content

        # Check for expected variables
        expected_variables = [
            "data_record",
            "categories",
            "context",
        ]

        for var in expected_variables:
            assert var in template_content

    def test_render_template_with_data(self):
        """Test rendering template with actual data."""
        variables = {
            "data_record": {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "555-1234"
            },
            "categories": ["high_value", "customer", "contact"],
            "context": "Customer data analysis"
        }

        rendered = render_template("data_classification.yaml", variables)

        assert isinstance(rendered, str)
        assert len(rendered) > 0
        assert "John Doe" in rendered
        assert "john@example.com" in rendered
        assert "high_value" in rendered
        assert "Customer data analysis" in rendered

    def test_render_template_missing_variables(self):
        """Test rendering template with missing variables raises error."""
        variables = {}  # Empty variables

        with pytest.raises(ValueError, match="Missing required template variables"):
            render_template("data_classification.yaml", variables)

    def test_response_format_is_json_schema(self):
        """Test that response format follows JSON schema structure."""
        template = load_template("data_classification.yaml")
        response_format = template["response_format"]

        assert "type" in response_format
        assert response_format["type"] == "object"
        assert "properties" in response_format
        assert "required" in response_format

        # Check for expected response fields
        expected_fields = [
            "category",
            "confidence",
            "reasoning",
            "pii_detected",
        ]

        for field in expected_fields:
            assert field in response_format["properties"]

    def test_template_type_enum(self):
        """Test that TemplateType enum has correct values."""
        assert TemplateType.DATA_CLASSIFICATION == "data_classification"
        assert TemplateType.PII_DETECTION == "pii_detection"
        assert TemplateType.CONFIDENCE_ASSESSMENT == "confidence_assessment"

    def test_get_template_metadata(self):
        """Test getting template metadata without loading full template."""
        metadata = get_template_metadata("data_classification.yaml")

        assert isinstance(metadata, dict)
        assert "name" in metadata
        assert "version" in metadata
        assert "description" in metadata
        assert "type" in metadata

    def test_load_nonexistent_template(self):
        """Test loading nonexistent template raises error."""
        with pytest.raises(FileNotFoundError):
            load_template("nonexistent_template.yaml")

    def test_render_invalid_template_syntax(self):
        """Test rendering template with invalid Jinja2 syntax."""
        # Create a temporary invalid template in the templates directory
        templates_dir = Path("/home/carlos/projects/data_foundry/data-foundry/src/core/prompts/templates")
        temp_filename = "invalid_test_template.yaml"
        temp_path = templates_dir / temp_filename

        invalid_template_content = """
        metadata:
          name: "Invalid Template"
          version: "1.0.0"
          description: "Test template with invalid syntax"
          type: "test"
          author: "Test"
          created_at: "2024-12-20"
        template: "Hello {{ name"  # Missing closing brace

        response_format:
          type: "object"
          properties: {}
          required: []
        """

        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(invalid_template_content)

            with pytest.raises(ValueError, match="Invalid Jinja2 template syntax"):
                render_template(temp_filename, {"name": "test"})
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_template_variables_validation(self):
        """Test that template variables are properly validated."""
        template = load_template("data_classification.yaml")

        # Template should define required variables
        assert "required_variables" in template["metadata"]
        required_vars = template["metadata"]["required_variables"]

        assert isinstance(required_vars, list)
        assert len(required_vars) > 0

        # Check that required variables are actually in the template
        template_content = template["template"]
        for var in required_vars:
            # Variables can be used in different Jinja2 syntaxes
            found = (
                f"{{{{ {var}" in template_content or
                f"for {var}" in template_content or
                f"{var} in" in template_content or
                f"for category in {var}" in template_content
            )
            assert found, f"Variable '{var}' not found in template content"

    def test_template_version_format(self):
        """Test that template version follows semantic versioning."""
        metadata = get_template_metadata("data_classification.yaml")
        version = metadata["version"]

        # Check semantic versioning format (major.minor.patch)
        import re
        version_pattern = r'^\d+\.\d+\.\d+$'
        assert re.match(version_pattern, version), f"Version {version} doesn't follow semantic versioning"

    def test_data_classification_template_constants(self):
        """Test DataClassificationTemplate constants."""
        assert hasattr(DataClassificationTemplate, 'FILENAME')
        assert hasattr(DataClassificationTemplate, 'METADATA')

        assert DataClassificationTemplate.FILENAME == "data_classification.yaml"
        assert isinstance(DataClassificationTemplate.METADATA, dict)

        # Check that metadata matches the actual file
        actual_metadata = get_template_metadata(DataClassificationTemplate.FILENAME)
        assert DataClassificationTemplate.METADATA == actual_metadata

    def test_template_has_instructions(self):
        """Test that template includes clear instructions for AI."""
        template = load_template("data_classification.yaml")
        template_content = template["template"]

        # Check for instructional content
        instructional_keywords = [
            "please",
            "analyze",
            "classify",
            "evaluate",
            "provide",
        ]

        for keyword in instructional_keywords:
            assert keyword in template_content.lower()

    def test_template_has_example_context(self):
        """Test that template provides example or context."""
        template = load_template("data_classification.yaml")

        # Should have example or usage instructions
        assert "example" in template["template"].lower() or \
               "context" in template["template"].lower() or \
               "guidance" in template["template"].lower()